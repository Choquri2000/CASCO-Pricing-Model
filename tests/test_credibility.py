"""Tests for ``src.credibility`` — Bühlmann-Straub blending.

Why test credibility?
The whole point is to *shrink* noisy segment estimates toward the portfolio
mean. The classic bug was using **dollar exposure** for n_i,
which makes every segment fully credible (Z≈1). We assert that:

  * Z is in [0,1] and k > 0,
  * mean Z is meaningfully below 1 (i.e. real shrinkage, by policy count),
  * the credibility-blended Gini beats the raw observed-segment Gini out-of-time.

Run:  ``python -m tests.test_credibility``
"""

import numpy as np

from src import load_data
from src import segments as sg
from src import features as ft
from src import credibility as cr


def _split():
    raw = load_data.load_analysis_frame()
    raw = sg.add_segments(raw)
    raw = sg.build_segment_key(raw)
    feat = ft.build_features(raw)
    return ft.make_time_split(feat)


def test_z_in_unit_interval_and_k_positive():
    train, _ = _split()
    seg, mu, k = cr.buhlmann_straub(train)
    assert k > 0, "k = EPV/VPP must be positive"
    assert (seg["Z"] >= 0).all() and (seg["Z"] <= 1).all()


def test_mean_z_shows_real_shrinkage_not_full_credibility():
    # Using the policy count (not dollar exposure) gives meaningful shrinkage.
    # Had we used dollar exposure, the mean Z would be ~1.0 (the old bug).
    train, _ = _split()
    seg, _, _ = cr.buhlmann_straub(train)
    assert seg["Z"].mean() < 0.8, "mean Z must be well below 1 (real shrinkage)"


def test_blended_gini_beats_raw_out_of_time():
    train, test = _split()
    res, _, _, _ = cr.evaluate_out_of_time(train, test)
    raw = res.loc[res["model"] == "Raw observed segment PP", "gini"].iloc[0]
    blended = res.loc[res["model"] == "Credibility-blended PP", "gini"].iloc[0]
    assert blended >= raw - 1e-9, "blending toward the mean must not hurt ranking"


if __name__ == "__main__":
    import sys
    from tests import _harness
    sys.exit(_harness.run_module(sys.modules[__name__]))
