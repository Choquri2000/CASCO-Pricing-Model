"""Tests for ``src.frequency`` — the claim-count model.

Why test the frequency model?
Two things are easy to get silently wrong here:

  * the GLM offset (log exposure) **must be re-applied at prediction time**,
    otherwise the model predicts an annual rate instead of the expected count
    over the policy's actual time on risk;
  * the ranking metric: an unweighted Gini on raw counts rewards a model for
    ranking long/large policies above short/small ones. `gini_normalized`
    ranks the predicted *rate* and weights by exposure.

We also check that the pipeline runs, discriminates, and is scored against the
current premium as a baseline.

Run:  ``python -m tests.test_frequency``
"""

import numpy as np
import statsmodels.api as sm

from src import frequency as fr
from tests import _data


def _split():
    return _data.time_split()


def test_gini_of_constant_is_zero():
    y = np.array([0, 1, 0, 3, 2, 0])
    assert abs(fr.gini(y, np.full_like(y, y.mean()))) < 1e-12
    e = np.array([0.5, 1.0, 0.2, 1.0, 0.7, 0.9])
    assert fr.gini_normalized(y, np.full(len(y), 0.4) * e, e) == 0.0


def test_normalized_gini_ignores_pure_exposure_effects():
    # Claims proportional to exposure: predicting "exposure" carries no risk
    # information. The raw Gini still rewards it; the normalized Gini does not.
    rng = np.random.default_rng(0)
    e = rng.uniform(0.1, 1.0, 20_000)
    y = rng.poisson(0.6 * e)
    assert fr.gini(y, e) > 0.2
    assert abs(fr.gini_normalized(y, e, e)) < 1e-9
    # A genuine risk factor is still detected.
    risk = rng.uniform(0.5, 2.0, 20_000)
    y2 = rng.poisson(0.6 * e * risk)
    assert fr.gini_normalized(y2, risk * e, e) > 0.1


def test_poisson_deviance_nonnegative():
    y = np.array([0, 1, 2, 0, 3.0])
    mu = np.array([0.5, 1.0, 2.0, 0.5, 3.0])
    assert fr.poisson_deviance(y, mu) >= 0
    # Perfect prediction -> deviance ~ 0. The 1e-6 clip on mu leaves a small residual
    # (2e-6 per zero target), so we assert it is small, not exactly 0.
    assert fr.poisson_deviance(y, y) < 1e-3


def test_offset_must_be_reapplied_at_predict():
    # Forgetting the offset at scoring time predicts the annual claim rate, which
    # overstates the expected count for every part-year policy.
    train, test = _split()
    tr = train[train["exposure"] > 0]
    te = test[test["exposure"] > 0]
    Xtr, Xte = fr.prepare_X(tr, te)
    model = fr.fit_poisson(Xtr, tr["y_freq"].values, tr["exposure"].values)

    Xc_te = sm.add_constant(np.asarray(Xte, dtype=float), has_constant="add")
    pred_with = model.predict(Xc_te, offset=np.log(te["exposure"].values))   # correct
    pred_without = model.predict(Xc_te)                                       # buggy

    actual = te["y_freq"].sum()
    assert abs(pred_with.sum() - actual) / actual < 0.5
    assert abs(pred_with.sum() - actual) < abs(pred_without.sum() - actual), \
        "offset bug: without the offset the expected counts are mis-scaled"


def test_gbm_offset_round_trip():
    # A LightGBM model fitted with an init_score offset must add it back at predict.
    rng = np.random.default_rng(1)
    X = rng.random((5_000, 3))
    e = rng.uniform(0.1, 1.0, 5_000)
    y = rng.poisson(0.5 * e * np.exp(X[:, 0]))
    m = fr.fit_gbm(X, y, e)
    pred = fr.predict_gbm(m, X, e)
    assert abs(pred.sum() / y.sum() - 1) < 0.05


def test_train_and_evaluate_runs_and_discriminates():
    train, test = _split()
    res = fr.train_and_evaluate(train, test)
    # Both GLMs and the premium baseline are present; every model discriminates and
    # ranks claim frequency better than the current premium does.
    assert set(res["model"]).issuperset({"Poisson GLM", "NegBin GLM", "Current premium (baseline)"})
    is_base = res["model"] == "Current premium (baseline)"
    models = res.loc[~is_base, "gini"]
    assert (models > 0).all(), "frequency models must discriminate"
    assert (models > res.loc[is_base, "gini"].iloc[0]).all(), "models should out-rank the current premium"
    # Poisson and NegBin must rank almost identically: the over-dispersion changes
    # the variance, not the ordering of risks. The loose tolerance still catches a
    # broken fit.
    poisson_g = res.loc[res["model"] == "Poisson GLM", "gini"].iloc[0]
    negbin_g = res.loc[res["model"] == "NegBin GLM", "gini"].iloc[0]
    assert abs(poisson_g - negbin_g) < 0.01, "NegBin and Poisson should rank risks alike"


if __name__ == "__main__":
    import sys
    from tests import _harness
    sys.exit(_harness.run_module(sys.modules[__name__]))
