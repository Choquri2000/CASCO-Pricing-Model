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
Segments with few policies / little earned premium produce noisy loss ratios.
We shrink the raw correction toward zero with a credibility factor so that we
do not over-react to thin data, and cap the final correction at
+/- `max_correction`.

    credibility      = min(1, earned_premium / full_credibility_premium)
    recommended_correction = clip(raw_correction * credibility, -max, +max)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Sensible defaults; tune to the portfolio / regulator
# constraints.
DEFAULT_TARGET_LOSS_RATIO = 0.60
DEFAULT_FULL_CREDIBILITY_PREMIUM = 5_000_000.0  # GEL of earned premium
DEFAULT_MAX_CORRECTION = 0.50  # +/- 50%

def recommend(
    seg_metrics: pd.DataFrame,
    target_loss_ratio: float = DEFAULT_TARGET_LOSS_RATIO,
    full_credibility_premium: float = DEFAULT_FULL_CREDIBILITY_PREMIUM,
    max_correction: float = DEFAULT_MAX_CORRECTION,
    earned_col: str = "earned_premium",
    loss_ratio_col: str = "loss_ratio",
    premium_rate_col: str = "premium_rate",
) -> pd.DataFrame:
    """Attach recommendation columns to a segment-metrics frame.

    Adds:
      - credibility
      - raw_correction
      - recommended_correction   (credibility-shrunk and capped)
      - recommended_premium_rate
      - recommended_rate_change_pct
      - action                   ("Increase" / "Decrease" / "Hold")
    """
    df = seg_metrics.copy()

    # Credibility: 0..1, based on earned premium vs the full-credibility standard.
    earned = df[earned_col].fillna(0.0)
    df["credibility"] = np.minimum(1.0, earned / full_credibility_premium)

    # Raw correction where we have a valid loss ratio; otherwise NaN
    # (no signal).
    lr = df[loss_ratio_col]
    raw = (lr / target_loss_ratio) - 1.0
    raw = raw.where(lr.notna() & (lr >= 0))

    # Shrink by credibility, then cap.
    shrunk = raw * df["credibility"]
    df["raw_correction"] = raw.round(4)
    df["recommended_correction"] = shrunk.clip(-max_correction, max_correction).round(4)

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
            "suminsured_usd_bin", "n_policies", "earned_premium",
            "loss_ratio", "premium_rate", "credibility",
            "recommended_correction", "recommended_rate_change_pct", "action",
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
