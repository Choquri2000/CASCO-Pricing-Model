"""Tests for ``src.pricing`` — model-based rate indication + elasticity.

Why test pricing?
This turns the model pure premium into a rate change. We assert that:

  * rate_change is capped in [-0.5, 0.5],
  * expected_volume_change == elasticity * rate_change,
  * the calibrated indication is positive on average (the book runs above the
    65% target loss ratio, so on balance it must be loaded).

Run:  ``python -m tests.test_pricing``
"""

import numpy as np

from src import pure_premium as pp
from src import pricing as pr
from tests import _data


def _indicated():
    train, test = _data.time_split(segmented=True)
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
    # The book runs above the 65% target loss ratio -> it must indicate an increase.
    rec = _indicated()
    assert rec["rate_change"].mean() > 0.0, "an under-priced book should be loaded on average"


if __name__ == "__main__":
    import sys
    from tests import _harness
    sys.exit(_harness.run_module(sys.modules[__name__]))
