# დოკუმენტაცია — `src/load_data.py`

> 🇬🇧 English version: [load_data.md](load_data.md)

**როლი:** ჩატვირთოს, გაწმინდოს და შეაერთოს 6 ნედლი წყარო ერთ პოლის-დონის ანალიზისთვის მზად ჩარჩოდ.
**დამოკიდებულება:** არაფერზე (საბაზისო მოდული). **გამოიყენება:** `segments`, `metrics`, `recommend`, `run`.

---

## 1. მოდულის კონსტანტები

| კონსტანტა | მნიშვნელობა | დანიშნულება |
|---|---|---|
| `DATA_DIR` | `../data` (ფაილის მიმართ ფარდობითი) | ყველა CSV წაკითხვა აჩვენებს აქ |
| `VALID_CLAIM_STATUSES` | `["Easy Settlement","Hard Settlement"]` | მხოლოდ ეს ზარალები ითვლება რეალიზებულ ზარალად |
| `ENRCOLS_COLS` | ქართული სვეტის სახელების სია | ქვესაერთოდ ჩატვირთული დიდი `enrcols.csv`-დან |
| `NONSTD_MARKER` | `"არასტანდარტული ფრანშიზა (დაუდგენლის გარეშე)"` | სიგნალი, რომელიც ნიშნავს "არასტანდარტული ფრანშიზა" |
| `NO_DEDUCTIBLE_CATEGORIES` | `{"Zero Deductible (All Risks)","No Deductible"}` | კატეგორიები, რომლებიც მაპირდება `deductible_type="No"`-ზე |

---

## 2. დაბალდონიანი წამკითხველები

### `_read_policies() -> DataFrame`
- კითხულობს `Policies_1805_v4.csv`.
- **ფილტრი (CASCO):** `df[df["licensename"].astype(str).str.contains("casco", case=False, na=False)]`.
- *სინტაქსის შენიშვნა:* `case=False` მას ხდის რეგისტრის-განურყოფს; `na=False` გამორიცხავს ნაკლულოვანს თანხმობისგან.

### `_read_clients()`, `_read_claims()`
- მარტივი `pd.read_csv(..., low_memory=False)`. `low_memory=False` თავიდან აირიდებს dtype გაფრთხილებებს შერეულ სვეტებზე.

### `_read_fx() -> DataFrame`
- კითხულობს `fx_rates.csv`, `parse_dates=["date"]`, შემდეგ `sort_values("date")` — **საჭიროა `merge_asof`-მდე**.

### `_read_enrcols() -> DataFrame`
- კითხულობს `enrcols.csv` `usecols=ENRCOLS_COLS` და `dtype={"id":"int64"}`-ით, რათა მეხსიერება დაბალი დარჩეს და id-ები ინტეგრის ტიპის იყოს.

---

## 3. ფრანშიზის (გამოკლების) გადაწყვეტა

### `_is_blank(v) -> bool`
```python
return pd.isna(v) or str(v).strip() == ""
```
ორივე `NaN`-ს და ცარიელ/გამორთულ სტრიქონს მიიჩნევს "მნიშვნელობის გარეშე".

### `_resolve_row(row) -> str | None`
ერთი პოლისის გამოკლების მნიშვნელობის პრიორიტეტი:
1. თუ `ფრანშიზის ველი` არ არის ცარიელი → დააბრუნე ის.
2. სხვაგვარად თუ `ფრანშიზა` ცარიელია → დააბრუნე `None`.
3. სხვაგვარად თუ `ფრანშიზა == NONSTD_MARKER` → დააბრუნე `არასტანდარტული ფრანში`, თუ არსებობს, სხვაგვარად `None`.
4. სხვაგვარად დააბრუნე `ფრანშიზა`.

### `_build_enrcols_features() -> DataFrame`
1. `enr["resolved_value"] = enr.apply(_resolve_row, axis=1).fillna("")`.
2. ჩატვირთე `franchise_field_categories.csv` → დატოვე `resolved_value → category`, `drop_duplicates("resolved_value")`.
3. `merge(lookup, on="resolved_value", how="left")`.
4. `deductible_category.fillna("No Deductible")` — **უსაფრთხო ნაგულისხმევი**, როცა lookup ვერ პოულობს.
5. `deductible_type = "No"` მხოლოდ თუ `category ∈ NO_DEDUCTIBLE_CATEGORIES`, სხვაგვარად `"Yes"`.
6. `drop_duplicates(subset=["id"])` → ერთი რიგი პოლისზე (enrcols არის ჯვარედინი ნაწარმოების ბაზა, id-ები მეორდება).
7. დააბრუნე სვეტები: `id, გამოყენება, deductible_type, deductible_category, დასახ. მძღოლების რაოდ, მძღოლის მინიმალური ასა`.

---

## 4. საჯარო API — `load_analysis_frame()`

აბრუნებს სრულად შეერთებულ ჩარჩოს. ოპერაციების რიგი:

### 4.1 FX ნორმალიზაცია (ფორმულა)
```
suminsured_usd = suminsuredgel / gel_per_usd
```
- `efdate` დაპარსულია datetime-ად, ჩარჩო დალაგებულია `efdate`-ით.
- `pd.merge_asof(left_on="efdate", right_on="date", direction="backward")` აერთიანებს **დღიურ** კურსს, რომელიც მოქმედია პოლისის დაწყებისას.
- *რატომ უკანა:* გამოიყენე ყველაზე ახლო წარსული კურსი მოცემული ძალის თარიღისთვის.

### 4.2 მიღებული ზარალები (ფორმულა)
```
incurred_claim(policy) = Σ reportedclaimamount   for calcclaimstatus ∈ VALID_CLAIM_STATUSES
n_claims(policy)       = ამ ზარალების რაოდენობა
```
მარცხნიდან შეუერთდა პოლისებს; ნაკლულოვანი → `incurred_claim=0`, `n_claims=0`.

### 4.3 ფიზიკური კლიენტების ფილტრი
დატოვე `clientstatus`, რომელიც შეიცავს `"ფიზიკურ"`-ს; მარცხნიდან-შეუერთე `age, gender, subsegmentkey, subsegmentname`.

### 4.4 ფრანშიზა + პირადი გამოყენება
მარცხნიდან შეუერთე enrcols ფიჩერები `policyid = id`-ზე; დატოვე მხოლოდ `გამოყენება`, რომელიც შეიცავს `"პირად"`-ს.

### 4.5 ძალით ჩაგდება და ფარდობები (ფორმულები)
```
premium_rate_gel = grosswrittenpremiumgel / suminsuredgel
loss_ratio       = incurred_claim / earned_premium      (NaN სადაც earned_premium <= 0)
```

---

## 5. გამოსავლის სქემა (ძირითადი სვეტები)
`policyid, clientid, efdate, suminsuredgel, suminsured_usd, earned_premium,
grosswrittenpremiumgel, incurred_claim, n_claims, age, gender, deductible_type,
deductible_category, premium_rate_gel, loss_ratio, …` (სულ 47 სვეტი).

## 6. ვერიფიკაციის ჩეკლისტი (იხ. `tests/test_load_data.py`)
- [x] ჩარჩო = 119,745 რიგი
- [x] `policyid`/`clientid` უნიკალური; enrcols დედუპლირებულია 1 რიგი/id-ზე
- [x] CASCO ფილტრი თანხვევა ნედლს vs წამკითხველს
- [x] `suminsured_usd` 0 ნული; FX ხელით შემოწმება ზუსტი
- [x] `deductible_type="No"` მხოლოდ ნულოვანი გამოკლების კატეგორიებში (No=106,049, Yes=13,696)
- [x] ზარალების ჯამი ემთხვევა სამაგალითო პოლისს
