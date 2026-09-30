"""Load, clean and join the raw CASCO data.

Steps:
1. Load the Policies / Claims / Clients / FX / enrcols CSV files.
2. Keep CASCO policies only, and only physical (individual) clients.
3. Normalise ``suminsured`` to USD using the daily FX rate on the policy
   effective date (``efdate``).
4. Aggregate valid claims (Easy/Hard Settlement) into an incurred amount per
   policy.
5. Resolve the deductible (franchise) field from enrcols and map it to a Yes/No
   ``deductible_type`` via ``franchise_field_categories.csv``.
6. Keep personal-use policies only (enrcols ``გამოყენება`` = "usage").
"""
# For hints #
from __future__ import annotations

import os
import numpy as np
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")

VALID_CLAIM_STATUSES = ["Easy Settlement", "Hard Settlement"]

# Georgian column names in the enrcols file. Only the relevant columns are loaded
# so that memory usage stays manageable (the file is ~1 GB).
ENRCOLS_COLS = [
    "id",
    "არხი",            # channel
    "ქვეარხი",         # sub-channel
    "სვალდებულო/ნებაყოფლობ",  # compulsory / voluntary
    "გამოყენება",      # usage (personal / commercial)
    "ფრანშიზის ველი",   # deductible field
    "ფრანშიზა",         # deductible
    "არასტანდარტული ფრანში",  # non-standard deductible
    "deductibletext",
    "მძღოლის მინიმალური ასა",  # minimum driver age
    "დასახ. მძღოლების რაოდ",   # number of named drivers
]

NONSTD_MARKER = "არასტანდარტული ფრანშიზა (დაუდგენლის გარეშე)"
NO_DEDUCTIBLE_CATEGORIES = {"Zero Deductible (All Risks)", "No Deductible"}


# --------------------------------------------------------------------------- #
# Raw readers
# --------------------------------------------------------------------------- #
def _read_policies() -> pd.DataFrame:
    df = pd.read_csv(os.path.join(DATA_DIR, "Policies_1805_v4.csv"), low_memory=False)
    # Keep CASCO policies only.
    df = df[df["licensename"].astype(str).str.contains("casco", case=False, na=False)].copy()
    return df


def _read_clients() -> pd.DataFrame:
    return pd.read_csv(os.path.join(DATA_DIR, "Clients_1805_v3.csv"), low_memory=False)


def _read_claims() -> pd.DataFrame:
    return pd.read_csv(os.path.join(DATA_DIR, "Claims_1805_v2.csv"), low_memory=False)


def _read_fx() -> pd.DataFrame:
    df = pd.read_csv(os.path.join(DATA_DIR, "fx_rates.csv"), parse_dates=["date"])
    return df.sort_values("date").reset_index(drop=True)


def _read_enrcols() -> pd.DataFrame:
    # Load only the required columns.
    return pd.read_csv(
        os.path.join(DATA_DIR, "enrcols.csv"),
        usecols=ENRCOLS_COLS,
        dtype={"id": "int64"},
        low_memory=False,
    )


# --------------------------------------------------------------------------- #
# Deductible (franchise) resolution -- logic taken from the task brief
# --------------------------------------------------------------------------- #
def _is_blank(v) -> bool:
    return pd.isna(v) or str(v).strip() == ""


def _resolve_row(row) -> str:
    veli = row["ფრანშიზის ველი"]
    if not _is_blank(veli):
        return veli
    franchiza = row["ფრანშიზა"]
    if _is_blank(franchiza):
        return None
    if str(franchiza).strip() == NONSTD_MARKER:
        nonstd = row["არასტანდარტული ფრანში"]
        return nonstd if not _is_blank(nonstd) else None
    return franchiza

# Load the deductible-category lookup. utf-8-sig strips the BOM so the first column
# name is not corrupted; then select resolved_value -> category, drop duplicates and rename.

def _build_enrcols_features() -> pd.DataFrame:
    enr = _read_enrcols()

    enr["resolved_value"] = enr.apply(_resolve_row, axis=1).fillna("")

    lookup = pd.read_csv(
        os.path.join(DATA_DIR, "franchise_field_categories.csv"),
        encoding="utf-8-sig",
    )[["resolved_value", "category"]].drop_duplicates("resolved_value").rename(
        columns={"category": "deductible_category"}
    )
    lookup["resolved_value"] = lookup["resolved_value"].fillna("")

    enr = enr.merge(lookup, on="resolved_value", how="left")
    enr["deductible_category"] = enr["deductible_category"].fillna("No Deductible")
    enr["deductible_type"] = np.where(
        enr["deductible_category"].isin(NO_DEDUCTIBLE_CATEGORIES), "No", "Yes"
    )

    # One row per policy id (enrcols contains duplicate rows per policy).
    keep = [
        "id",
        "გამოყენება",
        "deductible_type",
        "deductible_category",
        "დასახ. მძღოლების რაოდ",
        "მძღოლის მინიმალური ასა",
    ]
    enr = enr.drop_duplicates(subset=["id"])
    return enr[keep]


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def load_analysis_frame() -> pd.DataFrame:
    """Return the fully joined, analysis-ready policy-level frame."""
    # 1) Load the five sources
    policies = _read_policies()          # CASCO only
    clients = _read_clients()
    claims = _read_claims()
    fx = _read_fx()                      # daily GEL/USD
    enr = _build_enrcols_features()      # one row per policy (id)

    # 2) Convert sum insured to USD (FX)
    policies["efdate"] = pd.to_datetime(policies["efdate"], errors="coerce")  # date (bad -> NaT)
    pol_sorted = policies.sort_values("efdate").reset_index(drop=True)        # merge_asof needs sorted keys
    pol_sorted = pd.merge_asof(                                            # FX as of policy start (backward)
        pol_sorted, fx[["date", "gel_per_usd"]],
        left_on="efdate", right_on="date", direction="backward",
    )
    pol_sorted["suminsured_usd"] = pol_sorted["suminsuredgel"] / pol_sorted["gel_per_usd"]  # GEL -> USD
    policies = pol_sorted

    # 3) Aggregate claims per policy
    claims_valid = claims[claims["calcclaimstatus"].isin(VALID_CLAIM_STATUSES)].copy()  # valid only
    claims_valid["reportedclaimamount"] = pd.to_numeric(                               # amount as number
        claims_valid["reportedclaimamount"], errors="coerce")
    incurred = (                                                                       # sum + count per policy
        claims_valid.groupby("policyid")["reportedclaimamount"]
        .agg(incurred_claim="sum", n_claims="count").reset_index())
    df = policies.merge(incurred, on="policyid", how="left")  # every policy is kept
    df["incurred_claim"] = df["incurred_claim"].fillna(0.0)   # no claims -> 0
    df["n_claims"] = df["n_claims"].fillna(0).astype(int)     # no claims -> 0

    # 4) Attach physical-client attributes
    clients["clientstatus"] = clients["clientstatus"].astype(str)
    physical = clients[clients["clientstatus"].str.contains("ფიზიკურ", na=False)].copy()  # physical only
    df = df.merge(                                                                        # age/gender/segment
        physical[["clientid", "age", "gender", "subsegmentkey", "subsegmentname"]],
        on="clientid", how="left")

    # 5) Deductible enrichment + personal use only
    df = df.merge(enr, left_on="policyid", right_on="id", how="left")  # 1:1 enrichment
    df = df[df["გამოყენება"].astype(str).str.contains("პირად", na=False)].copy()  # personal-use filter

    # 6) Numeric types + derived ratios
    for col in ["earned_premium", "grosswrittenpremiumgel", "suminsuredgel", "age"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")              # to numeric
    df["premium_rate_gel"] = df["grosswrittenpremiumgel"] / df["suminsuredgel"]  # premium rate (GEL)
    df["loss_ratio"] = np.where(                                       # loss ratio (safe divide)
        df["earned_premium"] > 0, df["incurred_claim"] / df["earned_premium"], np.nan)

    return df



if __name__ == "__main__":
    frame = load_analysis_frame()
    print(f"Analysis frame shape: {frame.shape}")
    print(frame.head())
    print("\nLoss-ratio NaNs (no earned premium):", frame["loss_ratio"].isna().sum())
    print("Personal-use rows:", len(frame))
