"""Tests for ``src.segments`` — the four rating dimensions.

Why test segmentation?
Segmentation is the *business-rule* layer. A silent bug here (e.g. a bin that drops
a whole age range, or a vehicle type that was not mapped) makes the rate table
wrong without raising any error. We pin down that:

  * the four dimensions are generated,
  * the age bins cover the data without gaps (the 30-40 lesson),
  * vehicle types collapse into the three rating categories,
  * the composite ``segment`` key is unique per combination.

Run:  ``python -m tests.test_segments``
"""

import pandas as pd

from tests import _data


def _segmented():
    return _data.segmented_frame()


def test_four_dimensions_present():
    f = _segmented()
    for col in ["client_age_bin", "vehicle_type", "franchise", "suminsured_usd_bin", "segment"]:
        assert col in f.columns, f"missing {col}"


def test_age_bins_have_no_gap():
    # The brief fixes 18-20,21-25,26-29,>40; we added 30-40 so that 30-40 is not NaN.
    # "No gap" means the designed rating range (age >= 18) is fully covered
    # by contiguous bands with no hole (this was the 30-40 lesson). Ages below 18
    # (minors / data artefacts) are outside the rating range and
    # stay NaN by design.
    f = _segmented()
    age = pd.to_numeric(f["age"], errors="coerce")
    in_range = f[age >= 18]
    assert in_range["client_age_bin"].isna().sum() == 0, "every age >= 18 must be binned (no gap)"
    present = set(f["client_age_bin"].dropna().unique())
    assert present <= {"18-20", "21-25", "26-29", "30-40", ">40"}, f"unexpected age band(s): {present}"


def test_vehicle_type_collapsed_to_three_plus():
    # Residual rare types stay unchanged, but the three main categories must exist.
    f = _segmented()
    present = set(f["vehicle_type"].dropna().unique())
    for cat in ["მაღალი გამავლობის", "სედანი", "კუპე/კაბრიოლეტი"]:
        assert cat in present, f"expected rating category {cat}"


def test_franchise_is_binary():
    f = _segmented()
    assert set(f["franchise"].dropna().unique()) <= {"Yes", "No"}


def test_segment_key_unique_per_combination():
    f = _segmented()
    # Distinct (age, veh, fr, si) tuples must map to distinct segment strings.
    combos = f[["client_age_bin", "vehicle_type", "franchise", "suminsured_usd_bin"]].drop_duplicates()
    assert combos.shape[0] == f["segment"].nunique(), "segment key must be 1:1 with the 4-way combination"


if __name__ == "__main__":
    import sys
    from tests import _harness
    sys.exit(_harness.run_module(sys.modules[__name__]))
