"""Bühlmann-Straub credibility to stabilise segment pure premiums.

Classical credibility shrinks each segment's observed pure premium toward
the portfolio mean with weight Z_i = n_i / (n_i + k), where k = EPV / VPP:

  * EPV = exposure-weighted average within-segment variance of the pure premium
  * VPP = exposure-weighted variance of the segment means around the portfolio
          mean

Small / low-exposure segments get a low Z (strong shrinkage toward the mean);
large segments keep most of their own experience. The same Z can be used to
blend a model prediction with experience: Z * observed + (1 - Z) * model.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from . import segments as sg
from . import features as ft
from . import frequency as fr


def buhlmann_straub(frame, segment_col="segment",
                    exposure_col="earned_premium", cost_col="incurred_claim"):
    """Return (per-segment DataFrame, portfolio pure premium, k)."""
    f = frame.copy()
    exp = f[exposure_col].clip(lower=1e-6)
    f["pp"] = f[cost_col] / exp                         # policy-level pure premium
    g = f.groupby(segment_col, dropna=False)
    seg = pd.DataFrame({
        "exposure": g[exposure_col].sum(),
        "incurred": g[cost_col].sum(),
        "n_policies": g.size(),
        "mean_pp": g["pp"].mean(),
        "var_pp": g["pp"].var(),                        # within-segment variance
    })
    seg["observed_pp"] = seg["incurred"] / seg["exposure"].replace(0, np.nan)
    # Segments with a single policy have an undefined within-segment variance.
    seg["var_pp"] = seg["var_pp"].fillna(seg["var_pp"].median())

    # n_i = number of policies (the natural "number of observations"). Using
    # dollar exposure instead would make every segment fully credible (Z~1),
    # because the exposure totals are huge; the policy count gives meaningful shrinkage.
    n = seg["n_policies"].astype(float)
    mu = seg["incurred"].sum() / seg["exposure"].sum()  # portfolio pure premium
    epv = float(np.average(seg["var_pp"], weights=n))
    vpp = float(np.average((seg["mean_pp"] - mu) ** 2, weights=n))
    k = epv / vpp if vpp > 0 else np.inf

    seg["Z"] = n / (n + k)
    seg["cred_pp"] = seg["Z"] * seg["observed_pp"] + (1 - seg["Z"]) * mu
    return seg, mu, k


def evaluate_out_of_time(train, test):
    """Estimate credibility on `train`, carry the segment estimates to `test` and score the Gini."""
    seg_tr, mu, k = buhlmann_straub(train)
    test = test.copy()
    test["pred_observed"] = test["segment"].map(seg_tr["observed_pp"]).fillna(mu)
    test["pred_cred"] = test["segment"].map(seg_tr["cred_pp"]).fillna(mu)
    y = test["incurred_claim"] / test["earned_premium"].clip(lower=1e-6)
    rows = [
        {"model": "Constant (portfolio mean)", "gini": fr.gini(y, np.full(len(y), mu))},
        {"model": "Raw observed segment PP", "gini": fr.gini(y, test["pred_observed"])},
        {"model": "Credibility-blended PP", "gini": fr.gini(y, test["pred_cred"])},
    ]
    return pd.DataFrame(rows), seg_tr, mu, k


if __name__ == "__main__":
    import sys as _sys
    try:
        _sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    from .load_data import load_analysis_frame

    raw = load_analysis_frame()
    raw = sg.add_segments(raw)
    raw = sg.build_segment_key(raw)
    feat = ft.build_features(raw)
    train, test = ft.make_time_split(feat)

    results, seg_tr, mu, k = evaluate_out_of_time(train, test)
    print(f"Portfolio pure premium (mu) = {mu:.4f},  k = {k:.4f}")
    print(f"Mean Z = {seg_tr['Z'].mean():.4f},  median Z = {seg_tr['Z'].median():.4f}")
    print("\nOut-of-time Gini (higher = better pure-premium ranking):")
    print(results.round(4).to_string(index=False))

    print("\nExample segments (largest exposure):")
    ex = seg_tr.sort_values("exposure", ascending=False).head(8)
    print(ex[["exposure", "observed_pp", "Z", "cred_pp"]].round(4).to_string())
