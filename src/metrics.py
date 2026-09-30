"""Loss-ratio and premium-rate metrics for CASCO risk segments.

Definitions (from the task brief):
  * loss ratio   = incurred claim amount / earned premium
  * policy rate  = gross written premium / sum insured

All monetary amounts are in GEL unless a column is explicitly in USD.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _safe_div(num: pd.Series, den: pd.Series) -> pd.Series:
    """Element-wise division that returns NaN (not inf) when the denominator
    is 0."""
    den = den.replace(0, np.nan)
    return num / den


def aggregate_by(
    df: pd.DataFrame,
    group_cols: list[str],
    earned_col: str = "earned_premium",
    incurred_col: str = "incurred_claim",
    gwp_col: str = "grosswrittenpremiumgel",
    si_col: str = "suminsuredgel",
    claims_col: str = "n_claims",
) -> pd.DataFrame:
    """Aggregate the policy-level frame to one row per segment
    combination.

    Produces the core actuarial metrics needed for a rate review:
      - n_policies, n_claims
      - earned_premium, incurred_claim, gross_written_premium
      - loss_ratio            = incurred / earned
      - premium_rate          = gwp / sum_insured  (portfolio level)
      - avg_premium_rate      = mean of each policy's gwp / sum_insured
      - frequency             = n_claims / n_policies
      - severity              = incurred / n_claims
    """
    grouped = df.groupby(group_cols, observed=True)

    out = grouped.agg(
        n_policies=(group_cols[0], "size"),
        n_claims=(claims_col, "sum"),
        earned_premium=(earned_col, "sum"),
        incurred_claim=(incurred_col, "sum"),
        gross_written_premium=(gwp_col, "sum"),
        sum_insured=(si_col, "sum"),
    ).reset_index()

    out["loss_ratio"] = _safe_div(out["incurred_claim"], out["earned_premium"])
    out["premium_rate"] = _safe_div(out["gross_written_premium"], out["sum_insured"])
    out["frequency"] = _safe_div(out["n_claims"], out["n_policies"])
    out["severity"] = _safe_div(out["incurred_claim"], out["n_claims"])

    # Average per-policy premium rate (robust to a few very large
    # policies).
    tmp = df.copy()
    tmp["_rate"] = _safe_div(tmp[gwp_col], tmp[si_col])
    avg_rate = tmp.groupby(group_cols, observed=True)["_rate"].mean().reset_index()
    out = out.merge(avg_rate.rename(columns={"_rate": "avg_premium_rate"}),
                    on=group_cols, how="left")

    # Round to four decimals for readability.
    for c in ["loss_ratio", "premium_rate", "avg_premium_rate", "frequency", "severity"]:
        out[c] = out[c].round(4)

    return out


def aggregate_overall(df: pd.DataFrame) -> pd.Series:
    """Portfolio-level totals and ratios (one-row summary)."""
    earned = df["earned_premium"].sum()
    incurred = df["incurred_claim"].sum()
    gwp = df["grosswrittenpremiumgel"].sum()
    si = df["suminsuredgel"].sum()
    n_pol = len(df)
    n_clm = df["n_claims"].sum()

    return pd.Series(
        {
            "n_policies": n_pol,
            "n_claims": n_clm,
            "earned_premium": earned,
            "incurred_claim": incurred,
            "gross_written_premium": gwp,
            "sum_insured": si,
            "loss_ratio": incurred / earned if earned else np.nan,
            "premium_rate": gwp / si if si else np.nan,
            "frequency": n_clm / n_pol if n_pol else np.nan,
            "severity": incurred / n_clm if n_clm else np.nan,
        }
    ).round(4)


if __name__ == "__main__":
    from .load_data import load_analysis_frame
    from .segments import add_segments, build_segment_key

    frame = load_analysis_frame()
    frame = add_segments(frame)
    frame = build_segment_key(frame)

    print("=== Portfolio total ===")
    print(aggregate_overall(frame).to_string())

    print("\n=== By composite segment (top 15 by earned premium) ===")
    seg = aggregate_by(frame, ["segment"]).sort_values(
        "earned_premium", ascending=False
    )
    with pd.option_context("display.max_rows", 15, "display.width", 200):
        print(seg.head(15).to_string(index=False))

    print("\n=== By client age band ===")
    print(aggregate_by(frame, ["client_age_bin"]).to_string(index=False))
