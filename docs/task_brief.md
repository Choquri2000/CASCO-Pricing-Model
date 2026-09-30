# Technical Task — CASCO Claims-Cost Model and Underwriting Recommendations

> 🇬🇪 ქართული ვერსია: [task_brief.ka.md](task_brief.ka.md)
>
> English translation of the original task brief provided by TBC Insurance. The data files are confidential and are not included in this repository.

## 1. Business problem and objectives

One of TBC's main products is motor insurance (CASCO). The current tariff is generic rather than granular. A policy's rate is based on the following parameters *(details in section 3)*:

client age, vehicle type, deductible (franchise), insured limit (market value)

**Objective** — a data-driven analysis of the risk segments where the current price does not match the actual loss experience. Price adjustments may go either way (+/−). The format of the recommendations is free.

The **loss ratio** is calculated as: `incurred claim amount / earned premium`

The **underwriting team** is responsible for assessing risks and structuring policy prices.

The **actuary / data scientist** is responsible for developing statistically sound methodologies and for building a data-driven recommendation framework.

You are free to choose any technology. What matters is the result: an assessment of the loss ratio across segments and tariff recommendations based on the expected loss ratio. Accordingly, the current tariff should be assessed against the historical loss ratio, and ideally you should show where prices can be adjusted and how. The policy rate is calculated as: `gross written premium / sum insured`

Please read the data specifications carefully and contact us with any questions.


## 2. Data

The data files are in the `data/` folder.
Data extraction date: `2026-05-15`.

### 2.1 `Policies_1805_v2.csv` — policy master
One row per CASCO policy. Key fields:

| Field | Meaning |
|---|---|
| `policyid`, `clientid` | identifiers |
| `efdate`, `todate`, `cancellationdate` | policy start, end and cancellation dates |
| `policystatusid`, `policystatus` | policy status (active/expired/cancelled etc.). May need correcting |
| `suminsured`, `suminsuredcurrency`, `code`, `suminsuredgel` | market value of the insured vehicle and the insured limit. Use `fx_rates.csv` to normalise currencies (to USD). The table also has a `maxrate` field, but `fx_rates` is more accurate and lets you convert any currency to USD. |
| `grosswrittenpremiumgel`, `earned_premium` | premium (amount payable) fields |
| `licenseid`/`licensename`, `sectorid`/`sectorname`, `directionid`/`directionname` | structural fields |
| `vehicletypeid`/`vehicletypename`, `vehiclemarkid`/`vehiclemarkname`, `vehiclemodelid`/`vehiclemodelname`, `enginecapacity`, `carage`, `istaxi` | vehicle data |
| `eligible_driver_count` | number of named drivers (the count in enrcols is more accurate than in this table). Field name: `დასახ. მძღოლების რაოდ` |

### 2.2 `Claims_1805.csv` — claims
One row per reported claim, linked via `policyid`.

| Field | Meaning |
|---|---|
| `reportedclaimid` | claim identifier |
| `accidenttypeid`, `accidenttypename` | accident type |
| `accidentdate` | accident date |
| `calcclaimstatus` | `VALID_CLAIM_STATUSES = ["Easy Settlement", "Hard Settlement"]` |
| `reportedclaimamount` | claim amount |

### 2.3 `Clients_1805.csv` — client master
One row per client (`clientid`).
Fields: `age`, `gender`,
`subsegmentkey`/`subsegmentname` (client segment; NA can be put into the Mass segment),
`clientstatus` (physical/legal person — only physical persons are needed).

### 2.4 enrcols policy enrichment file — `პოლისების ბაზა - Casco, MTPL, MPA_18-05-2026_12.37.05.csv`
**Warning:** this is a cross-product policy database covering the Casco, MTPL and MPA lines — not only Casco. It must be joined to the Casco policy universe on `id` = `policyid`, and only the relevant Casco rows/columns used; the rest of the file is out of scope. Relevant columns for this task include:

`არხი` (channel), `ქვეარხი` (sub-channel), `სვალდებულო/ნებაყოფლობ` (compulsory/voluntary),
`გამოყენება` (usage) — personal or commercial use (only personal-use policies are needed),
`ფრანშიზის ველი`, `ფრანშიზა`, `არასტანდარტული ფრანში`, `deductibletext` — several deductible fields. The processing logic is given in section 3.
`მძღოლის მინიმალური ასა` (minimum driver age), `დასახ. მძღოლების რაოდ` (number of named drivers)

You are not limited to these fields. If relevant, you may use other fields too.


### 2.5 `fx_rates.csv` — daily FX rates
`date`, `gel_per_usd`, `gel_per_eur`, `usd_per_gel`, `eur_usd`. Needed to normalise `suminsured` to a single currency, because it is recorded in the currency the policy was written in.

## 3. Additional information

Tariff-defining parameters:


**Client age:** 18-20, 21-25, 26-29, >40
**Vehicle type:** sedan (სედანი), off-road / SUV class (მაღალი გამავლობის), coupe (კუპე)
*The data contains other types too, but they are merged with the following logic:*
```python
df_policies["vehicletypename"] = df_policies["vehicletypename"].replace({
    "ჯიპი": "მაღალი გამავლობის",        # SUV        -> off-road/SUV class
    "პიკაპი": "მაღალი გამავლობის",      # pickup     -> off-road/SUV class
    "ვენი": "სედანი",                   # van        -> sedan
    "უნივერსალი": "სედანი",             # estate     -> sedan
    "ჰეტჩბეკი": "სედანი",               # hatchback  -> sedan
    "კუპე": "კუპე/კაბრიოლეტი",          # coupe      -> coupe/convertible
    "კაბრიოლეტი": "კუპე/კაბრიოლეტი",    # convertible -> coupe/convertible
})
```

**Deductible (franchise):** Yes, No (derived for this task from the enrcols deductible fields, but you are not restricted to it — you may propose a better split)
```python
df_policies_enrcols_v2 = pd.read_csv(
    "./data/enrcols.csv",
    dtype={"id": "int64"},
)

NONSTD_MARKER = "არასტანდარტული ფრანშიზა (დაუდგენლის გარეშე)"  # "non-standard deductible (without unidentified)"

def is_blank(v):
    return pd.isna(v) or str(v).strip() == ""

def resolve_row(row):
    veli = row["ფრანშიზის ველი"]
    if not is_blank(veli):
        return veli
    franchiza = row["ფრანშიზა"]
    if is_blank(franchiza):
        return None
    if str(franchiza).strip() == NONSTD_MARKER:
        nonstd = row["არასტანდარტული ფრანში"]
        return nonstd if not is_blank(nonstd) else None
    return franchiza

# 1. derive resolved_value on df_policies_enrcols_v2
df_policies_enrcols_v2["resolved_value"] = df_policies_enrcols_v2.apply(resolve_row, axis=1).fillna("")

# 2. bring in deductible_category via the lookup already saved at data/franchise_field_categories.csv
lookup = pd.read_csv("data/franchise_field_categories.csv", encoding="utf-8-sig")[
    ["resolved_value", "category"]
].drop_duplicates("resolved_value").rename(columns={"category": "deductible_category"})
lookup["resolved_value"] = lookup["resolved_value"].fillna("")

df_policies_enrcols_v2 = df_policies_enrcols_v2.merge(lookup, on="resolved_value", how="left")
df_policies_enrcols_v2["deductible_category"] = df_policies_enrcols_v2["deductible_category"].fillna("No Deductible")

# 3.
# "No" only for the unconditional zero-deductible / no-deductible cases;
# any rider means a real deductible amount applies under some claim scenario
NO_DEDUCTIBLE_CATEGORIES = {"Zero Deductible (All Risks)", "No Deductible"}

df_policies_enrcols_v2["deductible_type"] = np.where(
    df_policies_enrcols_v2["deductible_category"].isin(NO_DEDUCTIBLE_CATEGORIES),
    "No", "Yes",
)
```

**Insured limit (market value) — Sum Insured Bin:**
```python
bins = [0, 5_000] + list(range(6_000, 51_000, 1_000)) + [float("inf")]

labels = (
    ["SI<=5k"]
    + [f"{i}k<SI<={(i+1)}k" for i in range(5, 50)]
    + [">50k"]
)

df_policies["suminsured_usd_bin"] = pd.cut(
    df_policies["suminsured_usd"],
    bins=bins,
    labels=labels,
    right=True,
    include_lowest=True,
)
```
