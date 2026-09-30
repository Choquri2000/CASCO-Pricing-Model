"""Pure-premium model: expected claim cost per policy
(frequency x severity).

Two ways to build the pure premium E[claim cost] = E[N] * E[S]:

  1. Multiplicative (two-part): model frequency and severity separately,
     then multiply their predictions. This is the classic, interpretable
     approach and reuses the frequency/severity modules.
  2. Tweedie GBM (direct): model the full incurred_claim directly with a Tweedie
     distribution (mass at zero + continuous positive tail in one model). LightGBM
     supports objective="tweedie".

Both are evaluated out-of-time against the actual pure premium (incurred_claim) using
the insurance **Gini** (ranking power) and the **Tweedie deviance**.
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
              sample_weight=np.asarray(exposure, dtype=float))
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
# Orchestration
# --------------------------------------------------------------------------- #
def train_and_evaluate(train: pd.DataFrame, test: pd.DataFrame) -> pd.DataFrame:
    # ---- Frequency component (all policies with positive exposure) ----
    tr_f = train[train["exposure"] > 0].copy()
    te_f = test[test["exposure"] > 0].copy()
    Xtr_f, Xte_f = fr.prepare_X(tr_f, te_f)
    ytr_f, yte_f = tr_f["y_freq"].values, te_f["y_freq"].values
    etr_f, ete_f = tr_f["exposure"].values, te_f["exposure"].values

    freq_model = fr.fit_poisson(Xtr_f, ytr_f, etr_f)
    off_te_f = np.log(ete_f)
    Xc_te_f = sm.add_constant(np.asarray(Xte_f, dtype=float), has_constant="add")
    freq_pred = freq_model.predict(Xc_te_f, offset=off_te_f)   # E[N | features]

    # ---- Severity component (claim-bearing, positive payments) ----
    tr_s = train[(train["n_claims"] > 0) & (train["y_sev"] > 0)].copy()
    Xtr_s, _ = sv.prepare_X(tr_s, tr_s)
    ytr_s = tr_s["y_sev"].values
    sev_model = sv.fit_lognormal(Xtr_s, ytr_s)
    # Predict E[S | claim, features] for every test policy (feature-based).
    _, Xte_s_all = sv.prepare_X(tr_s, te_f)
    Xc_te_s_all = sm.add_constant(np.asarray(Xte_s_all, dtype=float), has_constant="add")
    sev_pred_all = np.exp(sev_model.predict(Xc_te_s_all))       # E[S | claim, features]

    # ---- Multiplicative pure premium ----
    pp_multiplicative = freq_pred * sev_pred_all                # E[N] * E[S]

    # ---- Direct Tweedie GBM on the full incurred amount ----
    tr_pp = train[train["exposure"] > 0].copy()
    te_pp = test[test["exposure"] > 0].copy()
    Xtr_p, Xte_p = fr.prepare_X(tr_pp, te_pp, add_log_exposure=True)
    ytr_pp, yte_pp = tr_pp["y_pp"].values, te_pp["y_pp"].values
    tweedie = fit_tweedie(Xtr_p, ytr_pp, tr_pp["exposure"].values)
    pp_tweedie = tweedie.predict(Xte_p)

    # ---- Evaluate against the actual pure premium (incurred_claim) ----
    y_actual = te_f["y_pp"].values
    rows = [
        {"model": "Frequency x Severity (GLM)",
         "gini": fr.gini(y_actual, pp_multiplicative),
         "tweedie_deviance": tweedie_deviance(y_actual, pp_multiplicative)},
        {"model": "Tweedie GBM (direct)",
         "gini": fr.gini(y_actual, pp_tweedie),
         "tweedie_deviance": tweedie_deviance(y_actual, pp_tweedie)},
    ]
    return pd.DataFrame(rows)


def predict(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    """Multiplicative pure-premium predictions for the test rows with exposure > 0.

    Returns an array aligned with `test[test['exposure'] > 0]`
    (same row order).
    """
    tr_f = train[train["exposure"] > 0].copy()
    te_f = test[test["exposure"] > 0].copy()
    Xtr_f, Xte_f = fr.prepare_X(tr_f, te_f)
    ytr_f = tr_f["y_freq"].values
    etr_f, ete_f = tr_f["exposure"].values, te_f["exposure"].values

    freq_model = fr.fit_poisson(Xtr_f, ytr_f, etr_f)
    off_te_f = np.log(ete_f)
    Xc_te_f = sm.add_constant(np.asarray(Xte_f, dtype=float), has_constant="add")
    freq_pred = freq_model.predict(Xc_te_f, offset=off_te_f)   # E[N | features]

    tr_s = train[(train["n_claims"] > 0) & (train["y_sev"] > 0)].copy()
    Xtr_s, _ = sv.prepare_X(tr_s, tr_s)
    ytr_s = tr_s["y_sev"].values
    sev_model = sv.fit_lognormal(Xtr_s, ytr_s)
    _, Xte_s_all = sv.prepare_X(tr_s, te_f)
    Xc_te_s_all = sm.add_constant(np.asarray(Xte_s_all, dtype=float), has_constant="add")
    sev_pred_all = np.exp(sev_model.predict(Xc_te_s_all))       # E[S | claim, features]

    return freq_pred * sev_pred_all


def calibration_factor(train: pd.DataFrame) -> float:
    """Portfolio-level balance factor: mean(actual incurred) / mean(predicted).

    `predict` returns expected claim cost per policy (E[N] * E[S]); the actual
     is `incurred_claim` (also cost per policy). Both are in the same unit,
     so this ratio rescales the multiplicative model to the observed loss level
     (the standard "balance property" calibration) before any rate indication.
    """
    pred = predict(train, train)
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

    y_actual = test[test["exposure"] > 0]["y_pp"].values
    base_gini = fr.gini(y_actual, np.full(len(y_actual), y_actual.mean()))
    print(f"\nBaseline (constant) Gini = {base_gini:.4f} "
          f"(should be ~0; higher Gini = better discrimination)")
