"""Pricing: model-based technical premium, rate indication and elasticity.

This is recommendation "v2": instead of the raw segment loss ratio used in
`recommend.py`, the indication is driven by the model pure premium
(`pure_premium.predict`). For each policy/segment we compute:

  * technical_premium = model_pure_premium / target_loss_ratio
    (equivalent to loading for expenses and profit: dividing by (1 − expenses − profit), which is built into target_loss_ratio)
  * rate_change = clip(technical_premium / current_premium - 1, +/- cap)
  * expected_volume_change = elasticity * rate_change   (price elasticity of demand)

The demand elasticity is an assumption (there is no longitudinal volume data here);
it is exposed as a parameter so it can be replaced with an empirically estimated
value.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import segments as sg
from . import features as ft
from . import pure_premium as pp


def recommend_v2(frame, pred_pp, target_loss_ratio: float = 0.65,
                 elasticity: float = -0.5, clip: float = 0.5):
    """Return the frame with a model-based technical premium and rate indication.

    `pred_pp` must be pure-premium predictions aligned with the `frame[frame['exposure'] > 0]`
    rows (as produced by `pure_premium.predict`).
    """
    f = frame.reset_index(drop=True).copy()
    pp_full = np.full(len(f), np.nan)
    mask = (f["exposure"] > 0).values
    pp_full[mask] = pred_pp
    f["model_pp"] = pp_full

    current_premium = f["earned_premium"].clip(lower=1e-6)
    f["current_lr"] = (f["incurred_claim"] / current_premium).clip(upper=5.0)
    f["model_lr"] = f["model_pp"] / current_premium

    # Technical premium, loaded for expenses + profit.
    f["technical_premium"] = f["model_pp"] / target_loss_ratio
    raw_change = f["technical_premium"] / current_premium - 1.0
    f["rate_change"] = raw_change.clip(-clip, clip)
    f["expected_volume_change"] = elasticity * f["rate_change"]
    return f


def summarize_segments(f, segment_col: str = "segment"):
    g = f.groupby(segment_col, dropna=False)
    out = pd.DataFrame({
        "n_policies": g.size(),
        "exposure": g["exposure"].sum(),
        "current_lr": g.apply(lambda d: d["incurred_claim"].sum() / d["earned_premium"].sum(), include_groups=False),
        "model_lr": g["model_lr"].mean(),
        "rate_change": g["rate_change"].mean(),
        "expected_volume_change": g["expected_volume_change"].mean(),
    })
    return out


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

    pred = pp.predict(train, test)            # aligned with test[exposure > 0]
    calib = pp.calibration_factor(train)      # rebalance the model level
    print(f"Calibration factor (train): {calib:.4f}")
    pred = pred * calib
    rec = recommend_v2(test, pred, target_loss_ratio=0.65)
    summ = summarize_segments(rec)

    print("Model-based rate recommendations (test set, by segment):")
    print(summ.round(4).to_string())
    print(f"\nMean indicated rate change : {rec['rate_change'].mean():.4f}")
    print(f"Mean expected volume change (elasticity=-0.5): "
          f"{rec['expected_volume_change'].mean():.4f}")
    print(f"Policies recommended for an increase (rate_change > 0.05): "
          f"{int((rec['rate_change'] > 0.05).sum())}")
    print(f"Policies recommended for a decrease (rate_change < -0.05): "
          f"{int((rec['rate_change'] < -0.05).sum())}")
