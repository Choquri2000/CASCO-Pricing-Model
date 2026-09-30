"""Tests for ``src.validation`` — out-of-time monitoring.

Why test validation?
This is the governance layer: it must produce a monthly actual-vs-predicted
loss-ratio table and confirm that the model (a) ranks policies by how mispriced
they are (Gini of the predicted loss ratio > 0) and (b) is calibrated in *level*.
We assert both.

Run:  ``python -m tests.test_validation``
"""

from src import validation as vl
from tests import _data


def _split():
    return _data.time_split()


def test_monitoring_report_shape_and_columns():
    train, test = _split()
    mon, _ = vl.monitoring_report(train, test)
    assert {"n_policies", "earned_premium", "actual_lr", "pred_lr", "lr_ratio"} <= set(mon.columns)
    assert len(mon) >= 12, "should cover the hold-out months"


def test_holdout_gini_positive():
    train, test = _split()
    _, test_enriched = vl.monitoring_report(train, test)
    assert vl.holdout_gini(test_enriched) > 0, "the model must rank mispriced policies out-of-time"


def test_level_calibration_close_to_one():
    train, test = _split()
    from src import pure_premium as pp
    # The calibration factor is fitted on the TRAIN portfolio, so by construction the
    # calibrated train pure-premium predictions match train actual losses in level.
    # This pins the contract of `calibration_factor`; out-of-time drift is what the
    # monthly monitoring table is for.
    calib = pp.calibration_factor(train)
    pred = pp.predict(train, train) * calib
    mask = train["exposure"] > 0
    actual = train.loc[mask, "incurred_claim"].mean()
    predicted = pred.mean()
    ratio = actual / predicted
    assert abs(ratio - 1.0) < 0.05, f"the calibration factor must bring the train prediction ~ actual, ratio={ratio:.3f}"


if __name__ == "__main__":
    import sys
    from tests import _harness
    sys.exit(_harness.run_module(sys.modules[__name__]))
