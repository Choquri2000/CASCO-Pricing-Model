"""Claim severity model: expected claim amount per claim
(conditional on a claim having occurred).

Fitted on claim-bearing policies only and evaluated out-of-time:
  1. LogNormal GLM (log link) — a Gaussian GLM on log(severity); the stable,
     standard choice for this heavy-tailed target.
  2. LightGBM challenger (objective = "gamma")

Evaluation uses the insurance Gini (severity ranking) and the Gamma
deviance (goodness of fit). A constant predictor has Gini = 0.

Note: a Gamma GLM was tried, but statsmodels' IRLS/bfgs breaks down on this
heavy-tailed severity (it blows up / falls into an inversely-ranked local
optimum), so the LogNormal GLM is used as the parametric baseline.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

from . import features as ft
from . import frequency as fr   # reuse prepare_X (feature preparation) and gini


# --------------------------------------------------------------------------- #
# Data preparation (delegates to frequency.prepare_X — single source of truth)
# --------------------------------------------------------------------------- #
def prepare_X(train: pd.DataFrame, test: pd.DataFrame, add_log_exposure: bool = False):
    return fr.prepare_X(train, test, add_log_exposure=add_log_exposure)


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
def fit_lognormal(X, y, weights=None):
    # Models log(severity) with a Gaussian GLM (equivalent to a lognormal with a log link).
    Xc = sm.add_constant(np.asarray(X, dtype=float))
    ly = np.log(np.asarray(y, dtype=float))
    return sm.GLM(ly, Xc, family=sm.families.Gaussian()).fit(disp=0)


def fit_gbm(X, y, weights=None):
    try:
        import lightgbm as lgb
    except ImportError:
        raise RuntimeError("lightgbm is not installed; run `pip install lightgbm`")
    model = lgb.LGBMRegressor(
        objective="gamma", n_estimators=300, learning_rate=0.05,
        num_leaves=31, min_child_samples=50, verbose=-1,
    )
    w = None if weights is None else np.asarray(weights, dtype=float)
    model.fit(np.asarray(X, dtype=float), np.asarray(y, dtype=float), sample_weight=w)
    return model


# --------------------------------------------------------------------------- #
# Evaluation
# --------------------------------------------------------------------------- #
def gamma_deviance(y_true, y_pred) -> float:
    """Lower is better. y_pred are expected severities (must be > 0)."""
    y = np.asarray(y_true, dtype=float)
    mu = np.clip(np.asarray(y_pred, dtype=float), 1e-6, None)
    return 2.0 * float(np.sum(y / mu - np.log(y / mu) - 1.0))


def evaluate(models, Xte, yte, weights_te=None, Xte_gbm=None) -> pd.DataFrame:
    rows = []
    for name, m in models.items():
        if name == "GBM" and Xte_gbm is not None:
            pred = m.predict(Xte_gbm)                 # keep the DataFrame so feature names match
        elif name == "GBM":
            pred = m.predict(Xte)
        else:
            Xc = sm.add_constant(np.asarray(Xte, dtype=float), has_constant="add")
            if name == "LogNormal GLM":
                pred = np.exp(m.predict(Xc))          # back-transform log -> severity
            else:
                pred = m.predict(Xc)
        rows.append({
            "model": name,
            "gini": fr.gini(yte, pred),
            "gamma_deviance": gamma_deviance(yte, pred),
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def train_and_evaluate(train: pd.DataFrame, test: pd.DataFrame) -> pd.DataFrame:
    # Severity is conditional on a positive payment. Claims with n_claims > 0 but
    # incurred = 0 (zero-payment claims) are excluded here — they are already counted
    # by the frequency model, and Gamma/LogNormal/gamma-GBM all need y > 0.
    tr = train[(train["n_claims"] > 0) & (train["y_sev"] > 0)].copy()
    te = test[(test["n_claims"] > 0) & (test["y_sev"] > 0)].copy()
    # Weight each policy by its claim count for the GBM (more claims = more information).
    wtr = tr["n_claims"].clip(lower=1).values
    wte = te["n_claims"].clip(lower=1).values

    Xtr, Xte = prepare_X(tr, te)
    Xtr_g, Xte_g = prepare_X(tr, te, add_log_exposure=True)
    ytr, yte = tr["y_sev"].values, te["y_sev"].values

    models = {
        "LogNormal GLM": fit_lognormal(Xtr, ytr),
    }
    try:
        import lightgbm  # noqa: F401  (optional challenger)
        models["GBM"] = fit_gbm(Xtr_g, ytr, wtr)
    except ImportError:
        print("(lightgbm is not installed — GBM challenger skipped; install with `pip install lightgbm`)")

    return evaluate(models, Xte, yte, wte, Xte_gbm=Xte_g)


if __name__ == "__main__":
    from .load_data import load_analysis_frame

    feat = ft.build_features(load_analysis_frame())
    train, test = ft.make_time_split(feat)
    ntr = len(train[train["n_claims"] > 0])
    nte = len(test[test["n_claims"] > 0])
    print(f"Train with claims: {ntr}, test with claims: {nte}")

    results = train_and_evaluate(train, test)
    print("\nSeverity model — out-of-time evaluation (policies with claims):")
    print(results.round(4).to_string(index=False))

    yte_base = test[test["n_claims"] > 0]["y_sev"].values
    base_gini = fr.gini(yte_base, np.full(len(yte_base), yte_base.mean()))
    print(f"\nBaseline (constant) Gini = {base_gini:.4f} "
          f"(should be ~0; higher Gini = better discrimination)")
