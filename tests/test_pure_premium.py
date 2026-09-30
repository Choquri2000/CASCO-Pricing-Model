"""Tests for ``src.pure_premium`` — frequency × severity + Tweedie.

Why test the pure premium?
This is the core model (E[cost] = E[N]·E[S]) and the input to pricing. We check that:

  * tweedie_deviance >= 0 (and ~0 on a perfect fit),
  * calibration_factor is a sensible cost-to-cost ratio (~1.68),
  * predict() returns one value per test policy with exposure > 0,
  * train_and_evaluate discriminates (Gini > 0) for both models.

Run:  ``python -m tests.test_pure_premium``
"""

import numpy as np

from src import load_data
from src import features as ft
from src import pure_premium as pp


def _split():
    raw = load_data.load_analysis_frame()
    feat = ft.build_features(raw)
    return ft.make_time_split(feat)


def test_tweedie_deviance_nonnegative():
    y = np.array([0.0, 100.0, 500.0, 0.0, 200.0])
    mu = np.array([10.0, 110.0, 480.0, 5.0, 210.0])
    assert pp.tweedie_deviance(y, mu) >= 0
    # Perfect prediction -> deviance ~ 0. The 1e-6 clip on mu leaves a small
    # residual on zero targets (~4e-3 each), so we assert "small".
    assert pp.tweedie_deviance(y, y) < 1e-2


def test_calibration_factor_sensible():
    train, _ = _split()
    cf = pp.calibration_factor(train)
    # Documented value ~1.68; must be a positive, order-1 ratio.
    assert 1.0 < cf < 3.0, f"unexpected calibration factor: {cf}"


def test_predict_aligned_to_exposed_test_rows():
    train, test = _split()
    pred = pp.predict(train, test)
    n_exposed = int((test["exposure"] > 0).sum())
    assert len(pred) == n_exposed, "predict must align with test[exposure>0]"
    assert (pred > 0).all(), "expected pure premium must be positive"


def test_train_and_evaluate_discriminates():
    train, test = _split()
    res = pp.train_and_evaluate(train, test)
    assert set(res["model"]) == {"Frequency x Severity (GLM)", "Tweedie GBM (direct)"}
    assert (res["gini"] > 0).all()
    assert (res["tweedie_deviance"] >= 0).all()


if __name__ == "__main__":
    import sys
    from tests import _harness
    sys.exit(_harness.run_module(sys.modules[__name__]))
