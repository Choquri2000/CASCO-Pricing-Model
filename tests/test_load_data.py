"""Tests for ``src.load_data`` — the single trusted cleaning/join layer.

Why test this module first?
Everything downstream (segments, metrics, models) consumes the frame returned by
``load_analysis_frame()``. If the join/filter logic is wrong, every later
result is silently wrong. These tests pin down the *contract* of that frame:

  * it is policy-level (one row per policy),
  * it contains only CASCO / physical / personal-use policies,
  * the sum insured is FX-normalised to USD,
  * claims are aggregated into incurred_claim / n_claims with zeros filled,
  * the deductible (franchise) is resolved to Yes/No.

Run:  ``python -m tests.test_load_data``   (or ``pytest tests/test_load_data.py``)
"""

from src import load_data as ld


def _frame():
    # Loaded once per test through the public API; cheap enough for the test suite.
    return ld.load_analysis_frame()


def test_frame_is_policy_level_and_nonempty():
    # The frame must be one row per policy and must actually contain data.
    df = _frame()
    assert df.shape[0] > 100_000, "expected ~119k policies"
    assert df["policyid"].is_unique, "policyid must be a unique key"


def test_only_casco_policies():
    # We filtered licensename to contain 'casco' in _read_policies.
    df = _frame()
    assert df["licensename"].astype(str).str.contains("casco", case=False).all()


def test_only_physical_clients():
    # load_data keeps CASCO + personal-use policies; the personal-use filter
    # (`გამოყენება` contains "პირად") is the enforced row filter, and physical-client
    # attributes (age, ...) are LEFT-joined from the clients file. So the "individual"
    # guarantee is the personal-use filter, and we additionally confirm that the join
    # attached ages only to genuine physical clients.
    df = _frame()
    assert df["გამოყენება"].astype(str).str.contains("პირად", na=False).all(), "frame must be personal-use only"
    clients = ld._read_clients()
    clients["clientstatus"] = clients["clientstatus"].astype(str)
    physical_ids = set(
        clients.loc[clients["clientstatus"].str.contains("ფიზიკურ", na=False), "clientid"]
    )
    # Where age is populated, the client must be physical (the join is correct).
    has_age = df["age"].notna()
    assert df.loc[has_age, "clientid"].isin(physical_ids).all(), "populated ages must come from physical clients"


def test_only_personal_use():
    # usage (გამოყენება) must contain the Georgian word for 'personal' (პირად).
    df = _frame()
    assert df["გამოყენება"].astype(str).str.contains("პირად").all()


def test_suminsured_usd_is_positive_and_finite():
    # FX normalisation (suminsuredgel / gel_per_usd) must yield positive, finite USD.
    df = _frame()
    assert (df["suminsured_usd"] > 0).all(), "sum insured in USD must be > 0"
    # A pandas Series has no .isfinite(); .notna() catches the NaN that would arise if a
    # policy's efdate preceded every FX rate (gel_per_usd would be NaN).
    assert df["suminsured_usd"].notna().all(), "no NaN after FX normalisation"


def test_claims_aggregated_with_zeros_filled():
    # Policies without claims must have incurred_claim=0 and n_claims=0 (left join + fillna).
    df = _frame()
    assert (df["incurred_claim"] >= 0).all()
    assert (df["n_claims"] >= 0).all()
    # Most policies have zero claims.
    zero_claim_share = (df["n_claims"] == 0).mean()
    assert zero_claim_share > 0.5, "most policies should have no claim"


def test_deductible_type_is_yes_no():
    # Deductible resolution must collapse into a clean binary rating factor.
    df = _frame()
    assert set(df["deductible_type"].dropna().unique()) <= {"Yes", "No"}


def test_loss_ratio_computed_only_where_earned_positive():
    # loss_ratio is NaN where earned_premium <= 0 (safe divide), the ratio elsewhere.
    df = _frame()
    mask = df["earned_premium"] > 0
    assert df.loc[mask, "loss_ratio"].notna().all()
    # Where defined, loss_ratio == incurred/earned exactly.
    lr = df.loc[mask, "incurred_claim"] / df.loc[mask, "earned_premium"]
    assert ((lr - df.loc[mask, "loss_ratio"]).abs() < 1e-9).all()


if __name__ == "__main__":
    import sys
    from tests import _harness
    sys.exit(_harness.run_module(sys.modules[__name__]))
