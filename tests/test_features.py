"""Tests for ``src.features`` — feature store + time-based split.

Why test the features?
This module defines the modelling contract: the targets (y_freq, y_sev, y_pp),
the exposure and — most importantly — the **time split**. A wrong split (e.g.
random) would leak the future and inflate every later Gini. We check that:

  * make_time_split has zero policy overlap and respects the cutoff,
  * y_sev is defined only where a claim occurred,
  * exposure is earned policy-years (not premium) and non-negative,
  * build_features engineers the expected columns.

Run:  ``python -m tests.test_features``
"""

import numpy as np
import pandas as pd

from src import features as ft
from tests import _data


def _feat():
    return ft.build_features(_data.analysis_frame())


def test_time_split_has_no_overlap_and_respects_cutoff():
    f = _feat()
    train, test = ft.make_time_split(f, cutoff="2025-01-01")
    # No policy appears in both (the split is on the immutable efdate).
    overlap = set(train["policyid"]) & set(test["policyid"])
    assert len(overlap) == 0, "the time split must not leak policies between train/test"
    # Every train row is strictly before the cutoff; every test row on/after it.
    ef_tr = pd.to_datetime(train["efdate"])
    ef_te = pd.to_datetime(test["efdate"])
    assert (ef_tr < pd.Timestamp("2025-01-01")).all()
    assert (ef_te >= pd.Timestamp("2025-01-01")).all()
    # train should be the larger, older book.
    assert len(train) > len(test)


def test_y_sev_only_where_claim_occurred():
    f = _feat()
    # y_sev = incurred_claim / n_claims. It must be NaN where there were zero claims
    # (undefined), and defined + non-negative where a claim occurred. It is not
    # strictly > 0, because a claim may have a zero/NaN reported amount (y_sev = 0).
    assert f.loc[f["n_claims"] == 0, "y_sev"].isna().all()
    claimed = f[f["n_claims"] > 0]
    assert claimed["y_sev"].notna().all(), "y_sev must be defined where a claim occurred"
    assert (claimed["y_sev"] >= 0).all(), "severity cannot be negative"


def test_exposure_is_earned_years():
    f = _feat()
    assert (f["exposure"] >= 0).all(), "exposure = earned policy-years, clipped at 0"
    assert np.allclose(f["exposure"], f["earned_years"].clip(lower=0)), "exposure must be time, not premium"


def test_build_features_engineering():
    f = _feat()
    for col in ["log_suminsured_usd", "vehicle_type", "exposure", "y_freq", "y_pp"]:
        assert col in f.columns
    # log1p keeps it finite and >= 0 even for a zero sum insured.
    assert (f["log_suminsured_usd"] >= 0).all()
    assert np.isfinite(f["log_suminsured_usd"]).all()


def test_get_matrices_shapes():
    f = _feat()
    X, yf, ys, yp, exp = ft.get_matrices(f)
    assert len(X) == len(yf) == len(yp) == len(exp)
    assert list(X.columns) == ft.NUMERIC_FEATURES + ft.CATEGORICAL_FEATURES


if __name__ == "__main__":
    import sys
    from tests import _harness
    sys.exit(_harness.run_module(sys.modules[__name__]))
