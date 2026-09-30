"""Underwriting / rate recommendations from segment loss ratios.

Core idea
---------
For each risk segment we compare its *observed* loss ratio with a target loss
ratio. A segment running hotter than target is under-priced and should be
loaded; one running cooler is over-priced and can be discounted.

    raw_correction   = (loss_ratio / target_loss_ratio) - 1
    recommended_premium_rate = current_premium_rate * (1 + recommended_correction)

Credibility
-----------
Segments with few claims produce noisy loss ratios, so the segment's own
indication is blended with the portfolio-wide indication (the complement of
credibility), and the result is capped at +/- `max_correction`:

    base_correction  = (portfolio_loss_ratio / target_loss_ratio) - 1
    credibility      = min(1, sqrt(n_claims / full_credibility_claims))
    recommended_correction = clip(Z * raw_correction + (1 - Z) * base_correction, -max, +max)

This is classical limited-fluctuation credibility. The default full-credibility
standard of 1,082 claims corresponds to being within 5% of the true frequency
with 90% probability. A thin segment therefore moves with the whole book
(which is under-priced), instead of defaulting to "no change".
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Sensible defaults; tune to the portfolio / regulator
# constraints.
DEFAULT_TARGET_LOSS_RATIO = 0.60
DEFAULT_FULL_CREDIBILITY_CLAIMS = 1_082  # P = 90%, k = 5% (limited-fluctuation standard)
DEFAULT_MAX_CORRECTION = 0.50  # +/- 50%

def recommend(
    seg_metrics: pd.DataFrame,
    target_loss_ratio: float = DEFAULT_TARGET_LOSS_RATIO,
    full_credibility_claims: float = DEFAULT_FULL_CREDIBILITY_CLAIMS,
    max_correction: float = DEFAULT_MAX_CORRECTION,
    portfolio_loss_ratio: float | None = None,
    earned_col: str = "earned_premium",
    incurred_col: str = "incurred_claim",
    claims_col: str = "n_claims",
    loss_ratio_col: str = "loss_ratio",
    premium_rate_col: str = "premium_rate",
) -> pd.DataFrame:
    """Attach recommendation columns to a segment-metrics frame.

    `portfolio_loss_ratio` is the complement of credibility; if not given it is
    computed from the segments themselves (total incurred / total earned).

    Adds:
      - credibility
      - raw_correction
      - base_correction          (portfolio-wide indication)
      - recommended_correction   (credibility-blended and capped)
      - relative_to_portfolio    (change relative to the portfolio-wide move)
      - recommended_premium_rate
      - recommended_rate_change_pct
      - action                   ("Increase" / "Decrease" / "Hold")
    """
    df = seg_metrics.copy()

    if portfolio_loss_ratio is None:
        portfolio_loss_ratio = df[incurred_col].sum() / df[earned_col].sum()
    base = portfolio_loss_ratio / target_loss_ratio - 1.0

    # Credibility: square-root rule on the segment's claim count, 0..1.
    n_claims = df[claims_col].fillna(0.0).clip(lower=0)
    df["credibility"] = np.minimum(1.0, np.sqrt(n_claims / full_credibility_claims))

    # Raw correction where we have a valid loss ratio; otherwise NaN
    # (no signal).
    lr = df[loss_ratio_col]
    raw = (lr / target_loss_ratio) - 1.0
    raw = raw.where(lr.notna() & (lr >= 0))

    # Blend with the portfolio indication, then cap.
    blended = df["credibility"] * raw + (1.0 - df["credibility"]) * base
    df["raw_correction"] = raw.round(4)
    df["base_correction"] = round(base, 4)
    df["recommended_correction"] = blended.clip(-max_correction, max_correction).round(4)
    # Change relative to the portfolio-wide move: > 0 means load this segment
    # more than the book as a whole, < 0 means less (its relativity improves).
    df["relative_to_portfolio"] = ((1.0 + df["recommended_correction"]) / (1.0 + base) - 1.0).round(4)

    # Recommended premium rate and % change.
    rate = df[premium_rate_col]
    df["recommended_premium_rate"] = (rate * (1.0 + df["recommended_correction"])).round(6)
    df["recommended_rate_change_pct"] = (df["recommended_correction"] * 100).round(2)

    # Action label.
    def _action(v):
        if pd.isna(v):
            return "No data"
        if v >= 0.05:
            return "Increase"
        if v <= -0.05:
            return "Decrease"
        return "Hold"

    df["action"] = df["recommended_correction"].apply(_action)
    return df


def summarize_recommendations(rec: pd.DataFrame) -> pd.DataFrame:
    """Compact view of the most material recommendations (by earned premium)."""
    cols = [
        c for c in [
            "segment", "client_age_bin", "vehicle_type", "franchise",
            "suminsured_usd_bin", "n_policies", "n_claims", "earned_premium",
            "loss_ratio", "premium_rate", "credibility", "raw_correction",
            "base_correction", "recommended_correction", "recommended_rate_change_pct",
            "relative_to_portfolio", "action",
        ] if c in rec.columns
    ]
    return rec[cols].sort_values("earned_premium", ascending=False)


if __name__ == "__main__":
    from .load_data import load_analysis_frame
    from .segments import add_segments, build_segment_key
    from .metrics import aggregate_by

    frame = load_analysis_frame()
    frame = add_segments(frame)
    frame = build_segment_key(frame)

    seg = aggregate_by(frame, ["segment"])
    rec = recommend(seg)
    print(summarize_recommendations(rec).head(20).to_string(index=False))
    print("\nActions:", rec["action"].value_counts().to_dict())
