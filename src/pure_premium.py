"""Pure-premium model: expected claim cost per policy
(frequency x severity).

Two ways to build the pure premium E[claim cost] = E[N] * E[S]:

  1. Multiplicative (two-part): model frequency and severity separately,
     then multiply their predictions. This is the classic, interpretable
     approach and reuses the frequency/severity modules.
  2. Tweedie GBM (direct): model the full incurred_claim directly with a Tweedie
     distribution (mass at zero + continuous positive tail in one model), with
     log(exposure) as an offset. LightGBM supports objective="tweedie".

Both are evaluated out-of-time against the actual cost (incurred_claim) using the
exposure-weighted insurance **Gini** (ranking power per policy-year) and the
**Tweedie deviance**, next to the current premium as a baseline.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

from . import features as ft
from . import frequency as fr
from . import severity as sv


# --------------------------------------------------------------------------- #
# Direct Tweedie model
# --------------------------------------------------------------------------- #
def fit_tweedie(X, y, exposure, power: float = 1.5):
    """Tweedie GBM with log(exposure) as an offset; predict with `frequency.predict_gbm`."""
    try:
        import lightgbm as lgb
    except ImportError:
        raise RuntimeError("lightgbm is not installed; run `pip install lightgbm`")
    model = lgb.LGBMRegressor(
        objective="tweedie", tweedie_variance_power=power,
        n_estimators=300, learning_rate=0.05,
        num_leaves=31, min_child_samples=50, verbose=-1,
    )
    model.fit(np.asarray(X, dtype=float), np.asarray(y, dtype=float),
              init_score=np.log(np.asarray(exposure, dtype=float)))
    return model


def tweedie_deviance(y_true, y_pred, power: float = 1.5) -> float:
    """Lower is better. Valid for 1 < power < 2. Non-negative; 0 when y == mu."""
    y = np.asarray(y_true, dtype=float)
    mu = np.clip(np.asarray(y_pred, dtype=float), 1e-6, None)
    p = power
    a = (y ** (2 - p) - y * (mu ** (1 - p))) / (1 - p)
    b = (y ** (2 - p) - mu ** (2 - p)) / (2 - p)
    return 2.0 * float(np.sum(a - b))


# --------------------------------------------------------------------------- #
# Two-part model
# --------------------------------------------------------------------------- #
def _two_part_predict(train: pd.DataFrame, test: pd.DataFrame, smearing: bool = True) -> np.ndarray:
    """E[N] * E[S] for the test rows with exposure > 0."""
    # ---- Frequency component (all policies with positive exposure) ----
    tr_f = train[train["exposure"] > 0].copy()
    te_f = test[test["exposure"] > 0].copy()
    Xtr_f, Xte_f = fr.prepare_X(tr_f, te_f)
    freq_model = fr.fit_poisson(Xtr_f, tr_f["y_freq"].values, tr_f["exposure"].values)
    Xc_te_f = sm.add_constant(np.asarray(Xte_f, dtype=float), has_constant="add")
    freq_pred = freq_model.predict(Xc_te_f, offset=np.log(te_f["exposure"].values))  # E[N | features]

    # ---- Severity component (claim-bearing, positive payments) ----
    tr_s = train[(train["n_claims"] > 0) & (train["y_sev"] > 0)].copy()
    Xtr_s, _ = sv.prepare_X(tr_s, tr_s)
    sev_model = sv.fit_lognormal(Xtr_s, tr_s["y_sev"].values)
    # Predict E[S | claim, features] for every test policy (feature-based).
    _, Xte_s_all = sv.prepare_X(tr_s, te_f)
    Xc_te_s_all = sm.add_constant(np.asarray(Xte_s_all, dtype=float), has_constant="add")
    sev_pred = sv.predict_lognormal(sev_model, Xc_te_s_all, smearing=smearing)

    return freq_pred * sev_pred                                     # E[N] * E[S]


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def train_and_evaluate(train: pd.DataFrame, test: pd.DataFrame) -> pd.DataFrame:
    te = test[test["exposure"] > 0].copy()
    y_actual = te["y_pp"].values
    exposure = te["exposure"].values

    # ---- Multiplicative pure premium ----
    pp_multiplicative = _two_part_predict(train, test)

    # ---- Direct Tweedie GBM on the full incurred amount ----
    tr = train[train["exposure"] > 0].copy()
    Xtr_p, Xte_p = fr.prepare_X(tr, te)
    tweedie = fit_tweedie(Xtr_p, tr["y_pp"].values, tr["exposure"].values)
    pp_tweedie = fr.predict_gbm(tweedie, Xte_p, exposure)

    # ---- Current premium as the baseline "model" ----
    pp_premium = fr.premium_baseline(y_actual, te["earned_premium"].values)

    rows = []
    for name, pred in [("Frequency x Severity (GLM)", pp_multiplicative),
                       ("Tweedie GBM (direct)", pp_tweedie),
                       ("Current premium (baseline)", pp_premium)]:
        rows.append({"model": name,
                     "gini": fr.gini_normalized(y_actual, pred, exposure),
                     "tweedie_deviance": tweedie_deviance(y_actual, pred)})
    return pd.DataFrame(rows)


def predict(train: pd.DataFrame, test: pd.DataFrame, smearing: bool = True) -> np.ndarray:
    """Multiplicative pure-premium predictions for the test rows with exposure > 0.

    Returns an array aligned with `test[test['exposure'] > 0]`
    (same row order). Each value is the expected claim cost over the policy's
    earned exposure, i.e. directly comparable with its earned premium.
    """
    return _two_part_predict(train, test, smearing=smearing)


def calibration_factor(train: pd.DataFrame, smearing: bool = True) -> float:
    """Portfolio-level balance factor: mean(actual incurred) / mean(predicted).

    `predict` returns expected claim cost per policy (E[N] * E[S]); the actual
    is `incurred_claim` (also cost per policy). This ratio rescales the
    multiplicative model to the observed loss level (the standard "balance
    property" step) before any rate indication. With the smearing correction the
    factor is close to 1; without it (the original version) it was ~1.68.
    """
    pred = predict(train, train, smearing=smearing)
    mask = train["exposure"] > 0
    actual = train.loc[mask, "incurred_claim"]
    return float(actual.mean() / pred.mean())


if __name__ == "__main__":
    from .load_data import load_analysis_frame

    feat = ft.build_features(load_analysis_frame())
    train, test = ft.make_time_split(feat)
    print(f"Policies with exposure — train: {len(train[train['exposure']>0])}, "
          f"test: {len(test[test['exposure']>0])}")

    results = train_and_evaluate(train, test)
    print("\nPure-premium model — out-of-time evaluation (actual = incurred_claim):")
    print(results.round(4).to_string(index=False))
    print(f"\nCalibration factor (train): with smearing {calibration_factor(train):.4f}, "
          f"without {calibration_factor(train, smearing=False):.4f}")
