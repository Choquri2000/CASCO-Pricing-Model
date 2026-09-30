"""Tests for ``src.recommend`` — experience-rating price corrections.

Why test the recommendations?
This is the Part A deliverable: a credibility-weighted, capped
correction per segment. What must hold:

  * corrections are bounded by the cap (no absurd rates),
  * credibility is in [0,1] and follows the square-root rule on claim counts,
  * the complement of credibility is the portfolio-wide indication: a thin
    segment moves with the book instead of defaulting to "no change",
  * direction: a segment whose LR >> target gets a positive correction, and the
    "no deductible" segment (known to be hot) is loaded above the book average.

Run:  ``python -m tests.test_recommend``
"""

import numpy as np
import pandas as pd

from src import metrics as mt
from src import recommend as rc
from tests import _data


def _rec():
    f = _data.segmented_frame()
    seg = mt.aggregate_by(f, ["segment"])
    return rc.recommend(seg, portfolio_loss_ratio=mt.aggregate_overall(f)["loss_ratio"])


def test_corrections_within_cap():
    rec = _rec()
    # Segments with no earned premium yet have no loss ratio -> "No data", NaN correction.
    assert (rec.loc[rec["loss_ratio"].isna(), "action"] == "No data").all()
    corr = rec["recommended_correction"].dropna()
    assert (corr >= -0.50 - 1e-9).all()
    assert (corr <= 0.50 + 1e-9).all()


def test_credibility_in_unit_interval():
    rec = _rec()
    assert (rec["credibility"] >= 0).all() and (rec["credibility"] <= 1).all()


def test_complement_of_credibility_is_portfolio_indication():
    # Pure unit test (no data): a segment with no claims has zero credibility and
    # gets exactly the portfolio-wide correction; a fully credible one keeps its own.
    seg = pd.DataFrame({
        "earned_premium": [1000.0, 1000.0, 1000.0],
        "incurred_claim": [0.0, 900.0, 600.0],
        "n_claims": [0, 4_000, 270],
        "loss_ratio": [0.0, 0.9, 0.6],
        "premium_rate": [0.05, 0.05, 0.05],
    })
    rec = rc.recommend(seg, target_loss_ratio=0.60, portfolio_loss_ratio=0.72)
    base = 0.72 / 0.60 - 1
    assert rec.loc[0, "credibility"] == 0
    assert abs(rec.loc[0, "recommended_correction"] - round(base, 4)) < 1e-9
    assert rec.loc[1, "credibility"] == 1
    assert abs(rec.loc[1, "recommended_correction"] - 0.5) < 1e-9          # 0.9/0.6 - 1
    assert abs(rec.loc[2, "credibility"] - np.sqrt(270 / 1_082)) < 1e-9     # square-root rule


def test_thin_segments_shrink_toward_portfolio_indication():
    # A segment with few claims must have low credibility and a correction closer
    # to the portfolio-wide move than its own raw correction is.
    rec = _rec()
    base = rec["base_correction"].iloc[0]
    thin = rec[(rec["n_claims"] < 50) & rec["raw_correction"].notna()]
    if len(thin):
        assert (thin["credibility"] < np.sqrt(50 / 1_082) + 1e-9).all()
        dist_rec = (thin["recommended_correction"] - base).abs()
        dist_raw = (thin["raw_correction"] - base).abs()
        assert (dist_rec <= dist_raw + 1e-4).all()


def test_hot_segment_gets_positive_correction():
    # No-deductible segments run at ~74% LR vs the 60% target — they must be loaded,
    # and loaded more than the book as a whole.
    # When aggregated by `segment`, the deductible is embedded in the composite key
    # ("... | fr:No | ..."), not in a separate column, so we parse it from the string.
    rec = _rec()
    is_no = rec["segment"].str.contains("fr:No", regex=False)
    nod = rec[is_no]
    assert nod["recommended_correction"].mean() > 0, "no-deductible should be loaded"
    f = _data.segmented_frame()
    oneway = rc.recommend(mt.aggregate_by(f, ["franchise"]),
                          portfolio_loss_ratio=mt.aggregate_overall(f)["loss_ratio"])
    no = oneway.set_index("franchise").loc["No", "relative_to_portfolio"]
    assert no > 0, "no-deductible should be loaded above the portfolio-wide move"


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
