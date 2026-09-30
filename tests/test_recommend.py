"""Tests for ``src.recommend`` — experience-rating price corrections.

Why test the recommendations?
This is the Part A deliverable: a credibility-weighted, capped
correction per segment. Two things must hold:

  * corrections are bounded by the cap (no absurd rates),
  * credibility is in [0,1] and shrinks thin segments toward a zero correction.

We also check direction: a segment whose LR >> target gets a positive
correction (price up), and the "no deductible" segment (known to be hot) is loaded.

Run:  ``python -m tests.test_recommend``
"""

import numpy as np

from src import load_data
from src import segments as sg
from src import metrics as mt
from src import recommend as rc


def _rec():
    f = load_data.load_analysis_frame()
    f = sg.add_segments(f)
    f = sg.build_segment_key(f)
    seg = mt.aggregate_by(f, ["segment"])
    return rc.recommend(seg)


def test_corrections_within_cap():
    rec = _rec()
    assert (rec["recommended_correction"] >= -0.50 - 1e-9).all()
    assert (rec["recommended_correction"] <= 0.50 + 1e-9).all()


def test_credibility_in_unit_interval():
    rec = _rec()
    assert (rec["credibility"] >= 0).all() and (rec["credibility"] <= 1).all()


def test_credibility_shrinks_thin_segments():
    # A segment with little earned premium must have low credibility and a correction
    # strictly smaller (in magnitude) than its raw correction.
    rec = _rec()
    small = rec[rec["earned_premium"] < 200_000]
    if len(small):
        assert (small["credibility"] < 0.1).all()
        assert (small["recommended_correction"].abs() <= small["raw_correction"].abs() + 1e-9).all()


def test_hot_segment_gets_positive_correction():
    # No-deductible segments run at ~74% LR vs the 60% target — they must be loaded (positive).
    # When aggregated by `segment`, the deductible is embedded in the composite key
    # ("... | fr:No | ..."), not in a separate column, so we parse it from the string.
    rec = _rec()
    is_no = rec["segment"].str.contains("fr:No", regex=False)
    nod = rec[is_no]
    assert nod["recommended_correction"].mean() > 0, "no-deductible should be loaded"


def test_action_label_consistent_with_correction():
    rec = _rec()
    mask_inc = rec["recommended_correction"] >= 0.05
    mask_dec = rec["recommended_correction"] <= -0.05
    assert (rec.loc[mask_inc, "action"] == "Increase").all()
    assert (rec.loc[mask_dec, "action"] == "Decrease").all()


if __name__ == "__main__":
    import sys
    from tests import _harness
    sys.exit(_harness.run_module(sys.modules[__name__]))
