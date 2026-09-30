"""Tests for ``src.frequency`` — the claim-count model.

Why test the frequency model?
This is where the most important actuarial-coding bug was: the GLM
offset (log exposure) **must be re-applied at prediction time**, otherwise the model
predicts a per-unit-exposure rate instead of the expected count. We test that:

  * gini(constant) == 0  (the metric is correct),
  * poisson_deviance >= 0,
  * the OFFSET bug: predictions with the offset have a mean ~ the actual mean, while
    without the offset they are orders of magnitude smaller (rates, not counts),
  * the full train_and_evaluate pipeline runs and discriminates (Gini > 0).

Run:  ``python -m tests.test_frequency``
"""

import numpy as np
import pandas as pd
import statsmodels.api as sm

from src import load_data
from src import features as ft
from src import frequency as fr


def _split():
    raw = load_data.load_analysis_frame()
    feat = ft.build_features(raw)
    return ft.make_time_split(feat)


def test_gini_of_constant_is_zero():
    y = np.array([0, 1, 0, 3, 2, 0])
    assert abs(fr.gini(y, np.full_like(y, y.mean()))) < 1e-12


def test_poisson_deviance_nonnegative():
    y = np.array([0, 1, 2, 0, 3.0])
    mu = np.array([0.5, 1.0, 2.0, 0.5, 3.0])
    assert fr.poisson_deviance(y, mu) >= 0
    # Perfect prediction -> deviance ~ 0. The 1e-6 clip on mu leaves a small residual
    # (2e-6 per zero target), so we assert it is small, not exactly 0.
    assert fr.poisson_deviance(y, y) < 1e-3


def test_offset_must_be_reapplied_at_predict():
    # Reproduces the project's main bug fix: forgetting the offset at scoring time
    # predicts a per-unit-exposure rate (~0.00x), not the expected count.
    train, test = _split()
    tr = train[train["exposure"] > 0]
    te = test[test["exposure"] > 0]
    Xtr, Xte = fr.prepare_X(tr, te)
    ytr = tr["y_freq"].values
    etr, ete = tr["exposure"].values, te["exposure"].values
    model = fr.fit_poisson(Xtr, ytr, etr)

    off_te = np.log(ete)
    Xc_te = sm.add_constant(np.asarray(Xte, dtype=float), has_constant="add")
    pred_with = model.predict(Xc_te, offset=off_te)        # correct
    pred_without = model.predict(Xc_te)                    # buggy

    # With the offset, the mean prediction should be close to the observed mean count.
    assert abs(pred_with.mean() - te["y_freq"].mean()) / max(te["y_freq"].mean(), 1e-9) < 0.5
    # Without the offset the predictions are small rates, far below the actual mean.
    assert pred_without.mean() < 0.1 * pred_with.mean(), "offset bug: predictions are rates, not counts"


def test_train_and_evaluate_runs_and_discriminates():
    train, test = _split()
    res = fr.train_and_evaluate(train, test)
    # Both GLMs and the GBM are present; Gini must be positive (the model ranks risk).
    assert set(res["model"]).issuperset({"Poisson GLM", "NegBin GLM"})
    assert (res["gini"] > 0).all(), "frequency models must discriminate"
    # Poisson and NegBin must agree closely: with (near-)zero over-dispersion the
    # negative binomial collapses to the Poisson MLE, so their ranking power is
    # practically identical. The loose tolerance allows small numerical differences
    # but still catches a real divergence (e.g. a broken fit).
    poisson_g = res.loc[res["model"] == "Poisson GLM", "gini"].iloc[0]
    negbin_g = res.loc[res["model"] == "NegBin GLM", "gini"].iloc[0]
    assert abs(poisson_g - negbin_g) < 0.01, "NegBin should collapse to Poisson (no material over-dispersion)"


if __name__ == "__main__":
    import sys
    from tests import _harness
    sys.exit(_harness.run_module(sys.modules[__name__]))
