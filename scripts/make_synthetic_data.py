"""Generate a synthetic CASCO data set with the same schema as the confidential files.

The real TBC Insurance data cannot be published, so this script simulates a
portfolio from a small, documented risk model. No real record, customer or
company figure is used — only the file layout (column names, Georgian category
labels, date formats) mirrors the originals, so the whole pipeline and the test
suite run end to end on it.

The simulated "truth" is built so that the analysis has something to find:
  * claim frequency is higher for young drivers and sedans, lower with a deductible;
  * severity grows with vehicle value and with claims inflation over time;
  * the simulated *tariff* charges young drivers and sedans more but under-reacts,
    ignores the deductible, and is scaled to a ~70.6% portfolio loss ratio.

Usage:
    python scripts/make_synthetic_data.py                        # -> data/synthetic/
    python scripts/make_synthetic_data.py --out DIR --policies 20000 --seed 7

Then point the pipeline at it:
    CASCO_DATA_DIR=data/synthetic python -m src.run               # bash
    $env:CASCO_DATA_DIR = "data/synthetic"; python -m src.run     # PowerShell
"""

from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd

EXTRACTION_DATE = pd.Timestamp("2026-05-15")
TARGET_PORTFOLIO_LR = 0.705
NONSTD_MARKER = "არასტანდარტული ფრანშიზა (დაუდგენლის გარეშე)"

# Raw vehicle types (Georgian labels as in the brief) and their shares.
VEHICLE_TYPES = {
    "მაღალი გამავლობის": 0.50,   # off-road / SUV class
    "სედანი": 0.21,              # sedan
    "ჰეტჩბეკი": 0.19,            # hatchback -> sedan
    "ჯიპი": 0.02,                # SUV -> off-road class
    "უნივერსალი": 0.015,         # estate -> sedan
    "ვენი": 0.013,               # van -> sedan
    "კუპე": 0.008,               # coupe
    "პიკაპი": 0.007,             # pickup -> off-road class
    "კაბრიოლეტი": 0.003,         # convertible
    "ფურგონი": 0.002,            # cargo van (rare, left as is)
    "სპეციალიზებული": 0.002,     # special purpose (rare, left as is)
}
SEDAN_LIKE = {"სედანი", "ჰეტჩბეკი", "უნივერსალი", "ვენი"}
OFFROAD_LIKE = {"მაღალი გამავლობის", "ჯიპი", "პიკაპი"}
COUPE_LIKE = {"კუპე", "კაბრიოლეტი"}

# Deductible wordings (invented) and the category each maps to in the lookup.
ZERO_DEDUCTIBLE_TEXT = "ნულოვანი ფრანშიზა ყველა რისკის მიმართ"      # zero deductible, all risks
DEDUCTIBLE_TEXTS = {
    "ზარალის 10%, მინიმუმ 200 ლარი": "% of Loss w/ Minimum",        # 10% of loss, min GEL 200
    "ზარალის 5%, მინიმუმ 100 ლარი": "% of Loss w/ Minimum",         # 5% of loss, min GEL 100
    "დაზღვეული თანხის 1%": "Flat % of Sum Insured",                 # 1% of the sum insured
}
NONSTD_DEDUCTIBLE_TEXT = "ზარალის 10%, მინიმუმ 300 ლარი"           # 10% of loss, min GEL 300


def _choice(rng, options: dict, n: int):
    keys = list(options)
    p = np.array(list(options.values()), dtype=float)
    return rng.choice(keys, size=n, p=p / p.sum())


def make_fx(rng) -> pd.DataFrame:
    dates = pd.date_range("2019-01-01", "2026-06-30", freq="D")
    steps = rng.normal(0, 0.004, len(dates))
    level = np.empty(len(dates))
    level[0] = 2.70
    for i in range(1, len(dates)):                      # mean-reverting random walk
        level[i] = level[i - 1] + steps[i] + 0.002 * (2.75 - level[i - 1])
    gel_per_usd = np.clip(level, 2.45, 3.10)
    eur_usd = np.clip(1.10 + np.cumsum(rng.normal(0, 0.002, len(dates))) * 0.2, 1.0, 1.2)
    return pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "gel_per_usd": gel_per_usd.round(4),
        "gel_per_eur": (gel_per_usd * eur_usd).round(4),
        "usd_per_gel": (1 / gel_per_usd).round(6),
        "eur_usd": eur_usd.round(4),
    })


def make_clients(rng, n_clients: int) -> pd.DataFrame:
    status = _choice(rng, {"ფიზიკური": 0.955, "იურიდიული": 0.04, "Unknown": 0.005}, n_clients)
    physical = status == "ფიზიკური"
    age = np.where(physical, np.clip(rng.normal(44, 12, n_clients), 18, 85).round(), np.nan)
    age[physical & (rng.random(n_clients) < 0.002)] = np.nan          # a few missing ages
    gender = np.where(physical, _choice(rng, {"M": 0.60, "F": 0.35, "Unknown": 0.05}, n_clients), "Unknown")
    has_seg = rng.random(n_clients) < 0.2
    seg_key = np.where(has_seg, rng.choice([1, 2, 3], n_clients), np.nan)
    seg_name = pd.Series(seg_key).map({1: "Mass", 2: "Premium", 3: "Private"})
    return pd.DataFrame({
        "clientid": np.arange(100_000, 100_000 + n_clients),
        "age": age,
        "gender": gender,
        "subsegmentkey": seg_key,
        "subsegmentname": seg_name,
        "clientstatus": status,
    })


def make_portfolio(rng, n: int, clients: pd.DataFrame, fx: pd.DataFrame):
    # ---- policy attributes ------------------------------------------------
    policyid = np.arange(5_000_000, 5_000_000 + n)
    cl = clients.sample(n=n, replace=True, random_state=int(rng.integers(1_000_000_000))).reset_index(drop=True)
    start_days = (pd.Timestamp("2026-06-10") - pd.Timestamp("2020-01-01")).days
    efdate = pd.Timestamp("2020-01-01") + pd.to_timedelta(
        (np.sqrt(rng.random(n)) * start_days).astype(int), unit="D")    # growing volume
    todate = efdate + pd.Timedelta(days=364)
    cancelled = rng.random(n) < 0.20
    cancel = pd.Series(pd.NaT, index=range(n), dtype="datetime64[ns]")
    cancel[cancelled] = (efdate[cancelled]
                         + pd.to_timedelta(rng.integers(10, 360, cancelled.sum()), unit="D"))

    vtype = _choice(rng, VEHICLE_TYPES, n)
    carage = _choice(rng, {"10+": 0.43, "6-10": 0.38, "1-3": 0.11, "4-5": 0.08}, n)
    has_deductible = rng.random(n) < 0.11
    drivers = 1 + rng.poisson(1.1, n)
    engine = _choice(rng, {"2000": 0.3, "2500": 0.2, "1600": 0.15, "3000": 0.12,
                           "1800": 0.1, "3500": 0.08, "0": 0.05}, n)

    base_value = np.select([np.isin(vtype, list(OFFROAD_LIKE)), np.isin(vtype, list(COUPE_LIKE))],
                           [22_000, 25_000], 12_000)
    age_value = pd.Series(carage).map({"1-3": 1.8, "4-5": 1.4, "6-10": 1.0, "10+": 0.7}).values
    si_usd = np.clip(base_value * age_value * rng.lognormal(0, 0.55, n), 1_500, 250_000).round(-2)

    rate_at_start = pd.merge_asof(
        pd.DataFrame({"efdate": efdate}).reset_index().sort_values("efdate"),
        fx.assign(date=pd.to_datetime(fx["date"]))[["date", "gel_per_usd"]],
        left_on="efdate", right_on="date", direction="backward",
    ).sort_values("index")["gel_per_usd"].values
    si_gel = (si_usd * rate_at_start).round(2)
    currency = _choice(rng, {2: 0.79, 1: 0.20, 3: 0.01}, n)             # 1 GEL, 2 USD, 3 EUR

    # ---- time on risk ----------------------------------------------------
    end = pd.concat([pd.Series(todate), cancel], axis=1).min(axis=1).clip(upper=EXTRACTION_DATE)
    earned_years = ((end - efdate).dt.days / 365.25).clip(lower=0).values
    term_years = (todate - efdate).days.values / 365.25

    # ---- true risk -------------------------------------------------------
    age = cl["age"].values
    age_f = np.select([age <= 20, age <= 25, age <= 29, age <= 40], [1.25, 1.45, 1.40, 1.20], 0.95)
    age_f = np.where(np.isnan(age), 1.0, age_f)
    veh_f = np.select([np.isin(vtype, list(SEDAN_LIKE)), np.isin(vtype, list(COUPE_LIKE))], [1.15, 0.85], 0.95)
    ded_f = np.where(has_deductible, 0.75, 1.0)
    si_f = np.clip(1 + 0.10 * np.log(15_000 / si_usd), 0.7, 1.4)
    lam = 0.62 * age_f * veh_f * ded_f * si_f * rng.gamma(2.5, 1 / 2.5, n)
    n_claims = rng.poisson(lam * earned_years)

    # ---- claims --------------------------------------------------------------
    idx = np.repeat(np.arange(n), n_claims)
    years_since_2020 = (efdate[idx] - pd.Timestamp("2020-01-01")).days.values / 365.25
    mu = (np.log(900) + 0.35 * np.log(si_usd[idx] / 15_000)
          + 0.06 * years_since_2020 + np.where(has_deductible[idx], np.log(0.8), 0.0))
    amount = rng.lognormal(mu, 0.95)
    amount[rng.random(len(idx)) < 0.02] = 0.0                            # zero-payment claims
    status = _choice(rng, {"Easy Settlement": 0.47, "Hard Settlement": 0.41,
                           "Rejected": 0.11, "Open": 0.01}, len(idx))
    acc_offset = rng.random(len(idx)) * earned_years[idx] * 365.25
    claims = pd.DataFrame({
        "policyid": policyid[idx],
        "reportedclaimid": np.arange(9_000_000, 9_000_000 + len(idx)),
        "accidenttypeid": rng.integers(1, 6, len(idx)),
        "accidenttypename": _choice(rng, {"Collision": 0.6, "Glass": 0.2, "Theft": 0.05,
                                          "Natural hazard": 0.1, "Other": 0.05}, len(idx)),
        "accidentdate": (efdate[idx] + pd.to_timedelta(acc_offset.astype(int), unit="D")).strftime("%Y-%m-%d"),
        "calcclaimstatus": status,
        "reportedclaimamount": amount.round(2),
    })

    # ---- current tariff (imperfect by design) ----------------------------
    age_r = np.select([age <= 20, age <= 25, age <= 29, age <= 40], [2.0, 1.55, 1.30, 1.12], 1.0)
    age_r = np.where(np.isnan(age), 1.0, age_r)
    veh_r = np.select([np.isin(vtype, list(SEDAN_LIKE)), np.isin(vtype, list(COUPE_LIKE))], [1.40, 1.25], 0.95)
    si_r = (si_usd / 15_000) ** -0.25
    annual_premium = si_gel * 0.045 * age_r * veh_r * si_r               # deductible is not priced
    earned_fraction = np.where(term_years > 0, earned_years / term_years, 0.0)
    valid = claims["calcclaimstatus"].isin(["Easy Settlement", "Hard Settlement"])
    total_incurred = claims.loc[valid, "reportedclaimamount"].sum()
    scale = total_incurred / (TARGET_PORTFOLIO_LR * (annual_premium * earned_fraction).sum())
    gwp = (annual_premium * scale).round(2)
    earned_premium = (gwp * earned_fraction).round(2)

    status_policy = np.where(cancel.notna() & (cancel <= EXTRACTION_DATE), "Cancelled",
                             np.where(todate > EXTRACTION_DATE, "Active", "Expired"))
    fx_ccy = np.select([currency == 1, currency == 3], [1.0, rate_at_start * 1.1], rate_at_start)
    policies = pd.DataFrame({
        "policyid": policyid,
        "clientid": cl["clientid"].values,
        "efdate": efdate.strftime("%Y-%m-%d"),
        "todate": todate.strftime("%Y-%m-%d"),
        "cancellationdate": cancel.dt.strftime("%Y-%m-%d"),
        "policystatusid": pd.Series(status_policy).map({"Active": 1, "Expired": 2, "Cancelled": 3}).values,
        "policystatus": status_policy,
        "suminsured": (si_gel / fx_ccy).round(2),
        "suminsuredcurrency": currency,
        "code": pd.Series(currency).map({1: "GEL", 2: "USD", 3: "EUR"}).values,
        "maxrate": fx_ccy.round(4),
        "suminsuredgel": si_gel,
        "grosswrittenpremiumgel": gwp,
        "earned_premium": earned_premium,
        "licenseid": 1,
        "licensename": np.where(rng.random(n) < 0.97, "Casco", "MTPL"),
        "vehicletypename": vtype,
        "enginecapacity": engine,
        "istaxi": 0,
        "carage": carage,
        "eligible_driver_count": drivers,
    })
    return policies, claims, has_deductible, cl["age"].values


def make_enrcols(rng, policies: pd.DataFrame, has_deductible: np.ndarray, age: np.ndarray) -> pd.DataFrame:
    n = len(policies)
    veli = np.full(n, "", dtype=object)          # ფრანშიზის ველი (deductible field)
    franchiza = np.full(n, np.nan, dtype=object)  # ფრანშიზა (deductible)
    nonstd = np.full(n, np.nan, dtype=object)     # არასტანდარტული ფრანში (non-standard deductible)

    u = rng.random(n)
    no = ~has_deductible
    veli[no & (u < 0.70)] = ZERO_DEDUCTIBLE_TEXT
    franchiza[no & (u >= 0.70) & (u < 0.90)] = "ნულოვანი"                 # "zero"
    # the remaining no-deductible rows stay blank -> "No Deductible" by default
    texts = rng.choice(list(DEDUCTIBLE_TEXTS), n)
    veli[has_deductible & (u < 0.8)] = texts[has_deductible & (u < 0.8)]
    ns = has_deductible & (u >= 0.8)
    franchiza[ns] = NONSTD_MARKER
    nonstd[ns] = NONSTD_DEDUCTIBLE_TEXT

    min_age_choice = np.array([18, 21, 26, 30, 40])
    safe_age = np.where(np.isnan(age), 18, age)
    min_age = np.array([rng.choice(min_age_choice[min_age_choice <= a]) for a in safe_age])
    min_age_txt = np.where(rng.random(n) < 0.3, "", pd.Series(min_age).astype(str) + " წლიდან")  # "from N years"
    drivers_txt = np.where(rng.random(n) < 0.4, "", policies["eligible_driver_count"].astype(str))

    enr = pd.DataFrame({
        "id": policies["policyid"].values,
        "არხი": _choice(rng, {"Agency Network": 0.4, "Regions": 0.15, "Bank": 0.15,
                              "Direct": 0.1, "Leads": 0.1, "VIP": 0.1}, n),
        "ქვეარხი": pd.Series(rng.choice(["Retail", "Batumi", "Kutaisi"], n)).where(rng.random(n) >= 0.7).values,
        "სვალდებულო/ნებაყოფლობ": "Voluntary",
        "გამოყენება": _choice(rng, {"პირადი მოხმარება": 0.93, "კომერციული": 0.03,   # personal / commercial
                                     "ტაქსი": 0.02, "": 0.02}, n),              # taxi / missing
        "ფრანშიზის ველი": veli,
        "ფრანშიზა": franchiza,
        "არასტანდარტული ფრანში": nonstd,
        "deductibletext": np.where(veli != "", veli, nonstd),
        "მძღოლის მინიმალური ასა": min_age_txt,
        "დასახ. მძღოლების რაოდ": drivers_txt,
        "product": "Casco",
    })
    # Other product lines share the file (cross-product enrichment), plus a few duplicate ids.
    n_other = int(0.25 * n)
    other = enr.sample(n=n_other, random_state=1).assign(
        id=np.arange(8_000_000, 8_000_000 + n_other), product="MTPL", **{"სვალდებულო/ნებაყოფლობ": "Mandatory"})
    dups = enr.sample(frac=0.01, random_state=2)
    enr = pd.concat([enr, other, dups], ignore_index=True)
    enr["გამოყენება"] = enr["გამოყენება"].replace("", np.nan)
    return enr


def make_lookup() -> pd.DataFrame:
    rows = [(ZERO_DEDUCTIBLE_TEXT, "Zero Deductible (All Risks)"),
            ("ნულოვანი", "Zero Deductible (All Risks)"),
            (NONSTD_DEDUCTIBLE_TEXT, "% of Loss w/ Minimum")]
    rows += list(DEDUCTIBLE_TEXTS.items())
    lk = pd.DataFrame(rows, columns=["resolved_value", "category"])
    lk["riders"] = ""
    lk["source_column"] = "synthetic"
    lk["count"] = 0
    return lk


def main(out: str, n_policies: int, seed: int) -> None:
    rng = np.random.default_rng(seed)
    os.makedirs(out, exist_ok=True)
    fx = make_fx(rng)
    clients = make_clients(rng, int(n_policies / 2.2))
    policies, claims, has_ded, age = make_portfolio(rng, n_policies, clients, fx)
    enr = make_enrcols(rng, policies, has_ded, age)

    fx.to_csv(os.path.join(out, "fx_rates.csv"), index=False)
    clients.to_csv(os.path.join(out, "Clients_1805_v3.csv"), index=False)
    policies.to_csv(os.path.join(out, "Policies_1805_v4.csv"), index=False)
    claims.to_csv(os.path.join(out, "Claims_1805_v2.csv"), index=False)
    enr.to_csv(os.path.join(out, "enrcols.csv"), index=False)
    make_lookup().to_csv(os.path.join(out, "franchise_field_categories.csv"), index=False, encoding="utf-8-sig")
    print(f"Synthetic data written to {os.path.abspath(out)}: "
          f"{len(policies):,} policies, {len(claims):,} claims, {len(clients):,} clients.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "data", "synthetic"))
    ap.add_argument("--policies", type=int, default=130_000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    main(args.out, args.policies, args.seed)
