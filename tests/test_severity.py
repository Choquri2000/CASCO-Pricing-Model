"""Tests for ``src.severity`` — the claim-amount model (conditional on a claim).

Why test the severity model?
Severity is modelled on *positive* payments only; zero-payment claims
must be excluded (they break log/Gamma models and are already counted by frequency).
The LogNormal GLM must be back-transformed with the smearing factor, otherwise
it predicts the median claim instead of the mean and under-prices every policy.
We also check metric correctness and that the pipeline discriminates.

Run:  ``python -m tests.test_severity``
"""

import numpy as np
import statsmodels.api as sm

from src import severity as sv
from src import frequency as fr
from tests import _data


def _split():
    return _data.time_split()


def test_gini_of_constant_is_zero():
    # The insurance Gini is defined in `frequency` and reused here.
    y = np.array([100.0, 200.0, 150.0, 300.0])
    assert abs(fr.gini(y, np.full_like(y, y.mean()))) < 1e-12
    assert sv.severity_gini(y, np.full_like(y, 150.0), np.ones(4)) == 0.0


def test_gamma_deviance_nonnegative():
    y = np.array([100.0, 200.0, 50.0])
    mu = np.array([110.0, 190.0, 60.0])
    assert sv.gamma_deviance(y, mu) >= 0
    assert sv.gamma_deviance(y, y) < 1e-6


def test_training_target_has_no_zeros():
    # Severity is conditional on a positive payment; the training target must be > 0.
    train, _ = _split()
    tr = train[(train["n_claims"] > 0) & (train["y_sev"] > 0)]
    assert (tr["y_sev"] > 0).all()
    assert len(tr) > 1000, "enough claim-bearing policies to train on"


def test_lognormal_smearing_restores_the_mean():
    # exp(E[log S]) is the median; the smearing factor brings the mean back.
    train, _ = _split()
    tr = train[(train["n_claims"] > 0) & (train["y_sev"] > 0)]
    X, _ = sv.prepare_X(tr, tr)
    m = sv.fit_lognormal(X, tr["y_sev"].values)
    Xc = sm.add_constant(np.asarray(X, dtype=float))
    actual = tr["y_sev"].mean()
    assert m.smearing_factor > 1.0
    assert abs(sv.predict_lognormal(m, Xc).mean() / actual - 1) < 0.10, "smeared mean ~ actual mean"
    assert sv.predict_lognormal(m, Xc, smearing=False).mean() < 0.9 * actual, "unsmeared = median, too low"


def test_train_and_evaluate_runs_and_discriminates():
    train, test = _split()
    res = sv.train_and_evaluate(train, test)
    assert "LogNormal GLM" in set(res["model"])
    assert (res["gini"] > 0).all(), "severity models must discriminate"
    assert (res["gamma_deviance"] >= 0).all()


if __name__ == "__main__":
    import sys
    from tests import _harness
    sys.exit(_harness.run_module(sys.modules[__name__]))
