"""Tests for ``src.pricing`` — model-based rate indication + elasticity.

Why test pricing?
This turns the model pure premium into a rate change. The calibration factor
(cost-to-cost) is what points the indication in the right direction: without it
the under-priced book would (wrongly) suggest a cut. We assert that:

  * rate_change is capped in [-0.5, 0.5],
  * expected_volume_change == elasticity * rate_change,
  * the calibrated indication is positive on average (the book is under-priced vs target).

Run:  ``python -m tests.test_pricing``
"""

import numpy as np

from src import load_data
from src import segments as sg
from src import features as ft
from src import pure_premium as pp
from src import pricing as pr


def _indicated():
    raw = load_data.load_analysis_frame()
    raw = sg.add_segments(raw)
    raw = sg.build_segment_key(raw)
    feat = ft.build_features(raw)
    train, test = ft.make_time_split(feat)
    pred = pp.predict(train, test) * pp.calibration_factor(train)
    return pr.recommend_v2(test, pred, target_loss_ratio=0.65)


def test_rate_change_capped():
    rec = _indicated()
    # rate_change is NaN for zero-exposure rows (no model pure premium there),
    # so we only check the defined values against the +/-0.5 cap.
    rc = rec["rate_change"].dropna()
    assert (rc >= -0.5 - 1e-9).all()
    assert (rc <= 0.5 + 1e-9).all()


def test_volume_change_is_elasticity_times_rate_change():
    rec = _indicated()
    # expected_volume_change = elasticity * rate_change (default elasticity = -0.5).
    # Exclude NaN rate_change rows (zero exposure) before comparing.
    m = rec["rate_change"].notna()
    expected = -0.5 * rec.loc[m, "rate_change"]
    assert np.allclose(rec.loc[m, "expected_volume_change"], expected, atol=1e-9)


def test_calibrated_indication_is_positive_on_average():
    # The book runs at ~82% actual LR vs the 65% target -> it must indicate an increase.
    rec = _indicated()
    assert rec["rate_change"].mean() > 0.05, "an under-priced book should be loaded on average"


if __name__ == "__main__":
    import sys
    from tests import _harness
    sys.exit(_harness.run_module(sys.modules[__name__]))
