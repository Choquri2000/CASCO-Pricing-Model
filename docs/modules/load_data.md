# Documentation — `src/load_data.py`

> 🇬🇪 ქართული ვერსია: [load_data.ka.md](load_data.ka.md)

**Role:** load, clean and join the 6 raw sources into one policy-level, analysis-ready frame.
**Depends on:** nothing (base module). **Used by:** `segments`, `metrics`, `recommend`, `run`.

---

## 1. Module constants

| Constant | Value | Purpose |
|---|---|---|
| `DATA_DIR` | `../data` (relative to the file) | every CSV read points here |
| `VALID_CLAIM_STATUSES` | `["Easy Settlement","Hard Settlement"]` | only these claims count as incurred losses |
| `ENRCOLS_COLS` | list of Georgian column names | subset loaded from the large `enrcols.csv` |
| `NONSTD_MARKER` | `"არასტანდარტული ფრანშიზა (დაუდგენლის გარეშე)"` | marker meaning "non-standard deductible" |
| `NO_DEDUCTIBLE_CATEGORIES` | `{"Zero Deductible (All Risks)","No Deductible"}` | categories mapped to `deductible_type="No"` |

---

## 2. Low-level readers

### `_read_policies() -> DataFrame`
- Reads `Policies_1805_v4.csv`.
- **Filter (CASCO):** `df[df["licensename"].astype(str).str.contains("casco", case=False, na=False)]`.
- *Syntax note:* `case=False` makes it case-insensitive; `na=False` excludes missing values from the match.

### `_read_clients()`, `_read_claims()`
- Plain `pd.read_csv(..., low_memory=False)`. `low_memory=False` avoids dtype warnings on mixed columns.

### `_read_fx() -> DataFrame`
- Reads `fx_rates.csv` with `parse_dates=["date"]`, then `sort_values("date")` — **required before `merge_asof`**.

### `_read_enrcols() -> DataFrame`
- Reads `enrcols.csv` with `usecols=ENRCOLS_COLS` and `dtype={"id":"int64"}`, so memory stays low and ids are integers.

---

## 3. Deductible (franchise) resolution

### `_is_blank(v) -> bool`
```python
return pd.isna(v) or str(v).strip() == ""
```
Treats both `NaN` and empty/whitespace strings as "no value".

### `_resolve_row(row) -> str | None`
Priority for one policy's deductible value:
1. If `ფრანშიზის ველი` (deductible field) is not blank → return it.
2. Otherwise, if `ფრანშიზა` (deductible) is blank → return `None`.
3. Otherwise, if `ფრანშიზა == NONSTD_MARKER` → return `არასტანდარტული ფრანში` (non-standard deductible) if present, else `None`.
4. Otherwise return `ფრანშიზა`.

### `_build_enrcols_features() -> DataFrame`
1. `enr["resolved_value"] = enr.apply(_resolve_row, axis=1).fillna("")`.
2. Load `franchise_field_categories.csv` → keep `resolved_value → category`, `drop_duplicates("resolved_value")`.
3. `merge(lookup, on="resolved_value", how="left")`.
4. `deductible_category.fillna("No Deductible")` — **safe default** when the lookup finds nothing.
5. `deductible_type = "No"` only if `category ∈ NO_DEDUCTIBLE_CATEGORIES`, otherwise `"Yes"`.
6. `drop_duplicates(subset=["id"])` → one row per policy (enrcols is a cross-product database, ids repeat).
7. Return the columns: `id, გამოყენება, deductible_type, deductible_category, დასახ. მძღოლების რაოდ, მძღოლის მინიმალური ასა`.

---

## 4. Public API — `load_analysis_frame()`

Returns the fully joined frame. Order of operations:

### 4.1 FX normalisation (formula)
```
suminsured_usd = suminsuredgel / gel_per_usd
```
- `efdate` is parsed to datetime and the frame is sorted by `efdate`.
- `pd.merge_asof(left_on="efdate", right_on="date", direction="backward")` joins the **daily** rate in force at the policy start.
- *Why backward:* use the most recent past rate for a given effective date.

### 4.2 Incurred claims (formula)
```
incurred_claim(policy) = Σ reportedclaimamount   for calcclaimstatus ∈ VALID_CLAIM_STATUSES
n_claims(policy)       = number of those claims
```
Left-joined to the policies; missing → `incurred_claim=0`, `n_claims=0`.

### 4.3 Physical-client attributes
Select `clientstatus` containing `"ფიზიკურ"` (physical); left-join `age, gender, subsegmentkey, subsegmentname`.

### 4.4 Deductible + personal use
Left-join the enrcols features on `policyid = id`; keep only rows whose `გამოყენება` (usage) contains `"პირად"` (personal).

### 4.5 Type coercion and ratios (formulas)
```
premium_rate_gel = grosswrittenpremiumgel / suminsuredgel
loss_ratio       = incurred_claim / earned_premium      (NaN where earned_premium <= 0)
```

---

## 5. Output schema (main columns)
`policyid, clientid, efdate, suminsuredgel, suminsured_usd, earned_premium,
grosswrittenpremiumgel, incurred_claim, n_claims, age, gender, deductible_type,
deductible_category, premium_rate_gel, loss_ratio, …` (47 columns in total).

## 6. Verification checklist (see `tests/test_load_data.py`)
- [x] frame = 119,745 rows
- [x] `policyid`/`clientid` unique; enrcols de-duplicated to 1 row/id
- [x] CASCO filter reconciles raw vs reader
- [x] `suminsured_usd` has 0 nulls; FX spot-checked by hand
- [x] `deductible_type="No"` only in zero-deductible categories (No=106,049, Yes=13,696)
- [x] claim totals match a sample policy
