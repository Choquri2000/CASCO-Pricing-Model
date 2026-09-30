"""Features and time-based split for the CASCO pricing models.

This module turns the validated analysis frame (`load_data.load_analysis_frame`)
into a modelling frame:

  * numeric features: age, log(suminsured_usd) (log fixes the right skew),
    enginecapacity, min_driver_age, named_drivers.
  * categorical features: vehicle_type (collapsed to 3 categories), deductible_type, gender, carage.
  * exposure: earned policy-years (`earned_years`, used as the GLM offset and
    the GBM init_score offset). Earned premium is *not* used as exposure: it is
    GWP x earned fraction, so it already contains the current price that the
    models are meant to evaluate.
  * targets:
        y_freq = n_claims                      (frequency model)
        y_sev  = incurred_claim / n_claims     (severity model, claims > 0)
        y_pp   = incurred_claim                 (pure-premium / Tweedie model)

The split is strictly **time-based** (train = older policies, test = most recent)
to guard against leakage; it is not a random split.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import segments as sg

# Object-typed columns that are really numbers in the raw data.
_NUMERIC_COERCE = [
    "enginecapacity",
    "დასახ. მძღოლების რაოდ",   # number of named drivers
    "მძღოლის მინიმალური ასა",   # minimum driver age
]

# Features consumed by the models.
# Note: `carage` is stored as text bands in the raw data ("1-3", "4-5",
# "6-10", "10+") and is therefore used as a categorical feature (one-hot encoded
# in prepare_X). `min_driver_age` (enrcols "მძღოლის მინიმალური ასა") is ~55%
# empty, but the rest are real ages, so we keep it as a numeric feature —
# the gaps are median-imputed in prepare_X. `eligible_driver_count`
# is fully populated.
NUMERIC_FEATURES = [
    "age",
    "log_suminsured_usd",
    "enginecapacity",
    "named_drivers",
    "eligible_driver_count",
    "min_driver_age",
]
CATEGORICAL_FEATURES = ["vehicle_type", "deductible_type", "gender", "carage"]


def build_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Return the modelling frame with engineered features, exposure and
    targets."""
    f = frame.copy()

    # Collapse vehicle type into the three rating categories.
    f = sg.add_vehicle_type(f)

    # "მძღოლის მინიმალური ასა" arrives as text (e.g. "40 წლიდან" = "from 40 years");
    # extract the first number so it becomes numeric (gaps are median-imputed in prepare_X).
    _MDA = "მძღოლის მინიმალური ასა"
    if _MDA in f.columns:
        f[_MDA] = f[_MDA].astype(str).str.extract(r"(\d+)")[0]

    # Convert object-typed numbers (the raw data stores them as strings).
    for c in _NUMERIC_COERCE:
        f[c] = pd.to_numeric(f[c], errors="coerce")

    # Friendly names for the Georgian columns.
    f = f.rename(columns={
        "მძღოლის მინიმალური ასა": "min_driver_age",
        "დასახ. მძღოლების რაოდ": "named_drivers",
    })

    # Log-transform of sum insured (USD); log1p is safe at 0.
    f["log_suminsured_usd"] = np.log1p(f["suminsured_usd"].clip(lower=0))

    # Exposure = earned policy-years (must be >= 0 for the offset).
    f["exposure"] = f["earned_years"].clip(lower=0)

    # Targets.
    f["y_freq"] = f["n_claims"]
    f["y_sev"] = np.where(f["n_claims"] > 0, f["incurred_claim"] / f["n_claims"], np.nan)
    f["y_pp"] = f["incurred_claim"]

    return f


def make_time_split(
    frame: pd.DataFrame, cutoff: str = "2025-01-01"
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split on policy effective date. Train = before the cutoff, test = on or
    after it.

    Returns (train, test). The same policy cannot appear in both, because the
    split is on the immutable `efdate`.
    """
    ef = pd.to_datetime(frame["efdate"], errors="coerce")
    cut = pd.Timestamp(cutoff)
    train = frame[ef < cut].copy()
    test = frame[ef >= cut].copy()
    return train, test


def get_matrices(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.Series, pd.Series, pd.Series, pd.Series]:
    """Extract X, y_freq, y_sev, y_pp and exposure from a modelling frame."""
    cols = NUMERIC_FEATURES + CATEGORICAL_FEATURES
    X = df[cols].copy()
    return (
        X,
        df["y_freq"],
        df["y_sev"],
        df["y_pp"],
        df["exposure"],
    )


if __name__ == "__main__":
    from .load_data import load_analysis_frame

    raw = load_analysis_frame()
    feat = build_features(raw)
    train, test = make_time_split(feat)

    print("Modelling frame shape:", feat.shape)
    print(f"Train: {len(train)} rows (efdate < 2025-01-01)")
    print(f"Test : {len(test)} rows (efdate >= 2025-01-01)")
    print("Overlap (must be 0):", len(set(train["policyid"]) & set(test["policyid"])))

    print("\nFeature missing counts (train):")
    for c in NUMERIC_FEATURES + CATEGORICAL_FEATURES:
        n = int(train[c].isna().sum())
        if n:
            print(f"  {c}: {n} missing")

    print("\nExposure (earned policy-years) summary:")
    print(train["exposure"].describe().round(2).to_string())
    print("\nFrequency target (n_claims) summary:")
    print(train["y_freq"].describe().round(3).to_string())
