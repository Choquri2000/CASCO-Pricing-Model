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
    g = test.groupby("month")
    mon = pd.DataFrame({
        "n_policies": g.size(),
        "earned_premium": g["earned_premium"].sum(),
        "actual_lr": g.apply(lambda d: d["incurred_claim"].sum() / d["earned_premium"].sum(), include_groups=False),
        "pred_lr": g["pred_lr"].mean(),
    })
    mon["lr_ratio"] = mon["actual_lr"] / mon["pred_lr"]
    return mon, test


if __name__ == "__main__":
    from .load_data import load_analysis_frame

    raw = load_analysis_frame()
    feat = ft.build_features(raw)
    train, test = ft.make_time_split(feat)

    mon, test = monitoring_report(train, test)
    print("Monthly monitoring (test / holdout period) — actual vs predicted LR:")
    print(mon.round(4).to_string())

    y = test["incurred_claim"] / test["earned_premium"].clip(lower=1e-6)
    pred_lr = test["pred_lr"].fillna(test["pred_lr"].mean())
    print(f"\nTest insurance Gini (pure premium) : {fr.gini(y, pred_lr):.4f}")
    print(f"Test actual LR     : {y.mean():.4f}")
    print(f"Test predicted LR  : {pred_lr.mean():.4f}")
    print(f"Target LR          : 0.6500")
