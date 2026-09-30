"""Risk-segment derivation for the CASCO claims-cost / underwriting model.

This module turns the analysis-ready policy frame (`load_data.load_analysis_frame`)
into segments along the four rating / risk dimensions required by the task:

1. Client age band            -> `client_age_bin`
2. Vehicle type               -> `vehicle_type` (collapsed categories)
3. Deductible (franchise)     -> `deductible_type` ("Yes" / "No")  (created by load_data)
4. Sum insured (USD)          -> `suminsured_usd_bin`

The vehicle-type collapse and the sum-insured bands follow the snippets in the
task brief exactly, so the segmentation is reproducible.
"""

from __future__ import annotations

import pandas as pd

# ---------------------------------------------------------------------------
# 1. Vehicle-type collapse (verbatim from the task brief)
#    ჯიპი = SUV, პიკაპი = pickup, ვენი = van, უნივერსალი = estate,
#    ჰეტჩბეკი = hatchback, კუპე = coupe, კაბრიოლეტი = convertible;
#    მაღალი გამავლობის = off-road/SUV class, სედანი = sedan.
# ---------------------------------------------------------------------------
VEHICLE_TYPE_MAP = {
    "ჯიპი": "მაღალი გამავლობის",
    "პიკაპი": "მაღალი გამავლობის",
    "ვენი": "სედანი",
    "უნივერსალი": "სედანი",
    "ჰეტჩბეკი": "სედანი",
    "კუპე": "კუპე/კაბრიოლეტი",
    "კაბრიოლეტი": "კუპე/კაბრიოლეტი",
}

# ---------------------------------------------------------------------------
# 2. Client age bands
#    The brief lists: 18-20, 21-25, 26-29, >40.
#    We add an explicit 30-40 band so that ages 30-40 are not silently dropped
#    (">40" is strictly greater than 40, which would lose 30-40).
# ---------------------------------------------------------------------------
AGE_BINS = [18, 20, 25, 29, 40, float("inf")]
AGE_LABELS = ["18-20", "21-25", "26-29", "30-40", ">40"]

# ---------------------------------------------------------------------------
# 3. Sum-insured (USD) bands (verbatim from the task brief)
# ---------------------------------------------------------------------------
SI_BINS = [0, 5_000] + list(range(6_000, 51_000, 1_000)) + [float("inf")]
SI_LABELS = ["SI<=5k"] + [f"{i}k<SI<={(i + 1)}k" for i in range(5, 50)] + [">50k"]


def add_vehicle_type(df: pd.DataFrame, col: str = "vehicletypename") -> pd.DataFrame:
    """Collapse the raw vehicle-type name into the three rating categories."""
    df = df.copy()
    df["vehicle_type"] = df[col].replace(VEHICLE_TYPE_MAP)
    return df


def add_client_age_bin(df: pd.DataFrame, col: str = "age") -> pd.DataFrame:
    """Map client age into the rating age bands."""
    df = df.copy()
    age = pd.to_numeric(df[col], errors="coerce")
    df["client_age_bin"] = pd.cut(
        age, bins=AGE_BINS, labels=AGE_LABELS, right=True, include_lowest=True
    )
    return df


def add_suminsured_bin(df: pd.DataFrame, col: str = "suminsured_usd") -> pd.DataFrame:
    """Map the FX-normalised sum insured into USD bands."""
    df = df.copy()
    si = pd.to_numeric(df[col], errors="coerce")
    df["suminsured_usd_bin"] = pd.cut(
        si, bins=SI_BINS, labels=SI_LABELS, right=True, include_lowest=True
    )
    return df


def add_segments(df: pd.DataFrame) -> pd.DataFrame:
    """Add all four risk-segment dimensions to the analysis frame.

    Expects the columns produced by `load_data.load_analysis_frame`:
    `vehicletypename`, `age`, `suminsured_usd` and `deductible_type`.
    """
    df = add_vehicle_type(df)
    df = add_client_age_bin(df)
    df = add_suminsured_bin(df)
    # `deductible_type` ("Yes"/"No") already exists from load_data and is the
    # deductible dimension; expose a friendlier alias for downstream code.
    df["franchise"] = df["deductible_type"]
    return df


def build_segment_key(df: pd.DataFrame) -> pd.DataFrame:
    """Build a single composite segment label for group-by aggregation."""
    df = df.copy()
    df["segment"] = (
        "age:"
        + df["client_age_bin"].astype(str)
        + " | veh:"
        + df["vehicle_type"].astype(str)
        + " | fr:"
        + df["franchise"].astype(str)
        + " | si:"
        + df["suminsured_usd_bin"].astype(str)
    )
    return df


if __name__ == "__main__":
    from .load_data import load_analysis_frame

    frame = load_analysis_frame()
    frame = add_segments(frame)
    frame = build_segment_key(frame)

    print("Segmented frame shape:", frame.shape)
    print("\nClient age band counts:")
    print(frame["client_age_bin"].value_counts(dropna=False).sort_index())
    print("\nVehicle type counts:")
    print(frame["vehicle_type"].value_counts(dropna=False))
    print("\nDeductible counts:")
    print(frame["franchise"].value_counts(dropna=False))
    print("\nSum-insured USD band counts:")
    print(frame["suminsured_usd_bin"].value_counts(dropna=False).sort_index())
    print("\nDistinct composite segments:", frame["segment"].nunique())
