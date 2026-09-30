"""Out-of-time validation and monitoring for the CASCO pricing models.

Checks the pure-premium model on a time-based holdout and builds a monitoring
view: actual vs predicted loss ratio by calendar period, plus the insurance
Gini on the holdout. This is the governance/monitoring layer that would run
monthly in production to detect drift.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import features as ft
from . import pure_premium as pp
from . import frequency as fr


def monitoring_report(train, test, target_loss_ratio: float = 0.65):
    """Return (monthly monitoring DataFrame, enriched test frame)."""
    pred = pp.predict(train, test)
    calib = pp.calibration_factor(train)
    pred = pred * calib

    test = test.reset_index(drop=True).copy()
    mask = test["exposure"] > 0
    test["pred_pp"] = np.nan
    test.loc[mask, "pred_pp"] = pred
    test["pred_lr"] = test["pred_pp"] / test["earned_premium"].clip(lower=1e-6)
    test["actual_lr"] = test["incurred_claim"] / test["earned_premium"].clip(lower=1e-6)

    ef = pd.to_datetime(test["efdate"], errors="coerce")
    test["month"] = ef.dt.to_period("M").astype(str)
    # Both loss ratios are ratios of sums over the policies the model scores, so
    # actual and predicted are measured on the same basis.
    g = test[test["pred_pp"].notna()].groupby("month")
    mon = pd.DataFrame({
        "n_policies": g.size(),
        "earned_premium": g["earned_premium"].sum(),
        "actual_lr": g["incurred_claim"].sum() / g["earned_premium"].sum(),
        "pred_lr": g["pred_pp"].sum() / g["earned_premium"].sum(),
    })
    mon["lr_ratio"] = mon["actual_lr"] / mon["pred_lr"]
    return mon, test


def holdout_gini(test_enriched: pd.DataFrame) -> float:
    """Gini of the predicted loss ratio on the holdout, weighted by earned premium."""
    t = test_enriched[test_enriched["pred_pp"].notna() & (test_enriched["earned_premium"] > 0)]
    return fr.gini_normalized(t["incurred_claim"].values, t["pred_pp"].values, t["earned_premium"].values)


if __name__ == "__main__":
    from .load_data import load_analysis_frame

    raw = load_analysis_frame()
    feat = ft.build_features(raw)
    train, test = ft.make_time_split(feat)

    mon, test = monitoring_report(train, test)
    print("Monthly monitoring (test / holdout period) — actual vs predicted LR:")
    print(mon.round(4).to_string())

    print(f"\nTest insurance Gini (predicted LR, premium-weighted): {holdout_gini(test):.4f}")
    scored = test[test["pred_pp"].notna()]
    print(f"Test actual LR     : {scored['incurred_claim'].sum() / scored['earned_premium'].sum():.4f}")
    print(f"Test predicted LR  : {scored['pred_pp'].sum() / scored['earned_premium'].sum():.4f}")
    print(f"Target LR          : 0.6500")
