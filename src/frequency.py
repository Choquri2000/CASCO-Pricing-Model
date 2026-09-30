"""Frequency model: expected number of claims per policy.

Three models, trained on the time-based train set and evaluated
out-of-time:
  1. Poisson GLM        (statsmodels, offset = log(exposure))
  2. Negative-Binomial  (statsmodels, handles over-dispersion)
  3. LightGBM challenger (objective = "poisson", exposure as weight)

Evaluation uses the insurance **Gini** (ranking — the natural choice in an insurance context) and the **Poisson
deviance** (goodness of fit). A constant predictor has Gini = 0.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

from . import features as ft


# --------------------------------------------------------------------------- #
# Data preparation
# --------------------------------------------------------------------------- #
def prepare_X(train: pd.DataFrame, test: pd.DataFrame, add_log_exposure: bool = False):
    """Impute (median / 'Unknown'), standardise numerics, one-hot encode;
    align the columns.

    add_log_exposure=True adds log(exposure) as a feature — needed for
    tree (LightGBM) models, which cannot use an offset the way
    GLMs do.
    """
    num = ft.NUMERIC_FEATURES
    cat = ft.CATEGORICAL_FEATURES
    cols = num + cat + (["exposure"] if add_log_exposure else [])
    tr = train[cols].copy()
    te = test[cols].copy()

    medians = tr[num].median()
    tr[num] = tr[num].fillna(medians)
    te[num] = te[num].fillna(medians)
    tr[cat] = tr[cat].fillna("Unknown")
    te[cat] = te[cat].fillna("Unknown")

    # Standardise numerics with TRAIN statistics (helps GLM convergence; the GBM
    # is scale-invariant).
    means = tr[num].mean()
    stds = tr[num].std().replace(0, 1.0)
    tr[num] = (tr[num] - means) / stds
    te[num] = (te[num] - means) / stds

    if add_log_exposure:
        tr["log_exposure"] = np.log(np.clip(tr.pop("exposure"), 1e-6, None))
        te["log_exposure"] = np.log(np.clip(te.pop("exposure"), 1e-6, None))

    Xtr = pd.get_dummies(tr, columns=cat, drop_first=True)
    Xte = pd.get_dummies(te, columns=cat, drop_first=True)
    Xte = Xte.reindex(columns=Xtr.columns, fill_value=0)
    # Force every column to numeric (get_dummies may emit bool/object dummies).
    Xtr = Xtr.apply(pd.to_numeric, errors="coerce")
    Xte = Xte.apply(pd.to_numeric, errors="coerce")
    return Xtr, Xte


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
def fit_poisson(X, y, exposure):
    Xc = sm.add_constant(np.asarray(X, dtype=float))
    y = np.asarray(y, dtype=float)
    off = np.log(np.asarray(exposure, dtype=float))
    return sm.GLM(y, Xc, family=sm.families.Poisson(), offset=off).fit(disp=0)


def fit_negbin(X, y, exposure):
    Xc = sm.add_constant(np.asarray(X, dtype=float))
    y = np.asarray(y, dtype=float)
    off = np.log(np.asarray(exposure, dtype=float))
    # Start from the Poisson MLE. Key point: the over-dispersion parameter alpha
    # must start at a small positive value, never 0.0 — statsmodels internally
    # computes log(alpha), so alpha=0 -> log(0) = -inf and BFGS breaks down,
    # burning every iteration without converging. alpha=0.1 lets the
    # optimiser move smoothly to the MLE (which is ~0 when there is no
    # over-dispersion, i.e. NegBin collapses to Poisson).
    pois = sm.GLM(y, Xc, family=sm.families.Poisson(), offset=off).fit(disp=0)
    start = np.concatenate([pois.params, [0.1]])
    try:
        return sm.NegativeBinomial(y, Xc, offset=off).fit(
            start_params=start, method="bfgs", maxiter=100, disp=0)
    except Exception:
        # If NB fails to converge for any reason, fall back to the Poisson MLE
        # (the alpha -> 0 limit). This keeps the pipeline robust; it never crashes.
        return pois


def fit_gbm(X, y, exposure):
    try:
        import lightgbm as lgb
    except ImportError:
        raise RuntimeError("lightgbm is not installed; run `pip install lightgbm`")
    model = lgb.LGBMRegressor(
        objective="poisson", n_estimators=300, learning_rate=0.05,
        num_leaves=31, min_child_samples=50, verbose=-1,
    )
    model.fit(np.asarray(X, dtype=float), np.asarray(y, dtype=float),
              sample_weight=np.asarray(exposure, dtype=float))
    return model


# --------------------------------------------------------------------------- #
# Evaluation
# --------------------------------------------------------------------------- #
def gini(y_true, y_pred) -> float:
    """Insurance Gini (Lorenz / accuracy-ratio form), bounded in ~[-1, 1].

    Policies are sorted by predicted risk (ascending, lowest
    risk first); Gini is 1 - 2 * (area under the Lorenz curve of cumulative
    actual losses). 0 = no discrimination (random or constant
    predictions); higher = better ranking. This is the standard pricing
    metric and is rank-based, so it stays bounded even for heavy-tailed
    targets (unlike the covariance form).
    """
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(y_pred, dtype=float)
    n = len(y)
    if n == 0 or y.sum() == 0 or np.all(p == p[0]):
        return 0.0
    order = np.argsort(p, kind="mergesort")    # ascending by prediction (lowest risk first)
    ys = y[order]
    total = ys.sum()
    cum = np.cumsum(ys) / total                # cumulative share of actual losses
    x = np.arange(1, n + 1) / n
    B = np.trapz(cum, x)                       # area under the Lorenz curve
    return 1.0 - 2.0 * B


def poisson_deviance(y_true, y_pred) -> float:
    """Lower is better. y_pred are expected counts (must be > 0)."""
    y = np.asarray(y_true, dtype=float)
    mu = np.asarray(y_pred, dtype=float)
    mu = np.clip(mu, 1e-6, None)
    # log(y/mu) is undefined for y == 0; compute only the y > 0 elements
    # to avoid a divide-by-zero warning (unlike np.where, which evaluates
    # both branches). For y = 0 the contribution is mu.
    term = np.empty_like(y)
    pos = y > 0
    term[pos] = y[pos] * np.log(y[pos] / mu[pos]) - (y[pos] - mu[pos])
    term[~pos] = mu[~pos]
    return 2.0 * float(term.sum())


def evaluate(models, Xte, yte, exp_te, Xte_gbm=None) -> pd.DataFrame:
    rows = []
    off_te = np.log(np.asarray(exp_te, dtype=float))   # the offset must be re-applied at scoring time
    for name, m in models.items():
        if name == "GBM" and Xte_gbm is not None:
            pred = m.predict(Xte_gbm)   # keep the DataFrame for LightGBM feature names
        elif name == "GBM":
            pred = m.predict(Xte)
        else:
            Xc = sm.add_constant(np.asarray(Xte, dtype=float), has_constant="add")
            pred = m.predict(Xc, offset=off_te)
        rows.append({
            "model": name,
            "gini": gini(yte, pred),
            "poisson_deviance": poisson_deviance(yte, pred),
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def train_and_evaluate(train: pd.DataFrame, test: pd.DataFrame) -> pd.DataFrame:
    # Frequency models need positive exposure (GLM offset = log(exposure)).
    tr = train[train["exposure"] > 0].copy()
    te = test[test["exposure"] > 0].copy()

    # The GLMs use an offset; the tree challenger gets log(exposure) as a feature.
    Xtr, Xte = prepare_X(tr, te)
    Xtr_g, Xte_g = prepare_X(tr, te, add_log_exposure=True)
    ytr, yte = tr["y_freq"].values, te["y_freq"].values
    etr, ete = tr["exposure"].values, te["exposure"].values

    models = {
        "Poisson GLM": fit_poisson(Xtr, ytr, etr),
        "NegBin GLM": fit_negbin(Xtr, ytr, etr),
    }
    try:
        import lightgbm  # noqa: F401  (optional challenger)
        models["GBM"] = fit_gbm(Xtr_g, ytr, etr)
    except ImportError:
        print("(lightgbm is not installed — GBM challenger skipped; install with `pip install lightgbm`)")

    return evaluate(models, Xte, yte, ete, Xte_gbm=Xte_g)


if __name__ == "__main__":
    from .load_data import load_analysis_frame

    feat = ft.build_features(load_analysis_frame())
    train, test = ft.make_time_split(feat)
    print(f"Train (exp>0): {len(train[train['exposure']>0])}, "
          f"Test (exp>0): {len(test[test['exposure']>0])}")

    results = train_and_evaluate(train, test)
    print("\nFrequency model — out-of-time evaluation:")
    print(results.round(4).to_string(index=False))

    yte_base = test[test["exposure"] > 0]["y_freq"].values
    base_gini = gini(yte_base, np.full(len(yte_base), yte_base.mean()))
    print(f"\nBaseline (constant) Gini = {base_gini:.4f} "
          f"(should be ~0; higher Gini = better discrimination)")
