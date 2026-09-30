"""Tests for ``src.metrics`` — loss-ratio / rate aggregates.

Why test the metrics?
These aggregates feed the recommendation engine and the report. A divide-by-zero or
a mislabelled column propagates everywhere. We check that:

  * _safe_div returns NaN (not inf) for a zero denominator,
  * aggregate_by produces the core metrics and they are internally consistent
    (loss_ratio == incurred/earned, frequency == claims/policies),
  * aggregate_overall reproduces the known portfolio loss ratio (~0.706).

Run:  ``python -m tests.test_metrics``
"""

import numpy as np
import pandas as pd

from src import load_data
from src import segments as sg
from src import metrics as mt


def _seg():
    f = load_data.load_analysis_frame()
    f = sg.add_segments(f)
    f = sg.build_segment_key(f)
    return mt.aggregate_by(f, ["segment"])


def test_safe_div_returns_nan_not_inf():
    num = pd.Series([1.0, 2.0])
    den = pd.Series([2.0, 0.0])
    out = mt._safe_div(num, den)
    assert out.iloc[0] == 0.5
    assert np.isnan(out.iloc[1]), "a zero denominator must return NaN, never inf"


def test_aggregate_by_core_metrics_present():
    seg = _seg()
    for c in ["n_policies", "n_claims", "earned_premium", "incurred_claim",
              "loss_ratio", "frequency", "severity", "premium_rate"]:
        assert c in seg.columns


def test_aggregate_by_internally_consistent():
    seg = _seg()
    # loss_ratio must equal incurred/earned; frequency must equal claims/policies.
    lr = seg["incurred_claim"] / seg["earned_premium"]
    fr = seg["n_claims"] / seg["n_policies"]
    assert ((lr - seg["loss_ratio"]).abs() < 1e-3).all()
    assert ((fr - seg["frequency"]).abs() < 1e-3).all()


def test_portfolio_loss_ratio_known_value():
    f = load_data.load_analysis_frame()
    f = sg.add_segments(f)
    overall = mt.aggregate_overall(f)
    # The documented portfolio loss ratio is ~70.6%.
    assert abs(overall["loss_ratio"] - 0.706) < 0.02, "portfolio LR should be ~0.706"


if __name__ == "__main__":
    import sys
    from tests import _harness
    sys.exit(_harness.run_module(sys.modules[__name__]))
