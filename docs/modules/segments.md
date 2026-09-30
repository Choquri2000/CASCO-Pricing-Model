# Documentation — `src/segments.py`

> 🇬🇪 ქართული ვერსია: [segments.ka.md](segments.ka.md)

**Role:** derive the four risk-segment dimensions from the analysis frame.
**Depends on:** `load_data` (for the frame). **Used by:** `metrics`, `recommend`, `run`.

---

## 1. Segment dimensions

| Dimension | Derived column | Source |
|---|---|---|
| Client age | `client_age_bin` | `age` |
| Vehicle type | `vehicle_type` | `vehicletypename` (collapsed) |
| Deductible (franchise) | `franchise` (= `deductible_type`) | from `load_data` |
| Sum insured (USD) | `suminsured_usd_bin` | `suminsured_usd` |

---

## 2. Constants and formulas

### 2.1 Vehicle-type collapse (verbatim from the brief)
```python
VEHICLE_TYPE_MAP = {
    "ჯიპი": "მაღალი გამავლობის", "პიკაპი": "მაღალი გამავლობის",   # SUV, pickup -> off-road/SUV class
    "ვენი": "სედანი", "უნივერსალი": "სედანი", "ჰეტჩბეკი": "სედანი", # van, estate, hatchback -> sedan
    "კუპე": "კუპე/კაბრიოლეტი", "კაბრიოლეტი": "კუპე/კაბრიოლეტი",   # coupe, convertible -> coupe/convertible
}
```
Applied via `df["vehicle_type"] = df[col].replace(VEHICLE_TYPE_MAP)`.

### 2.2 Client age bands
```python
AGE_BINS  = [18, 20, 25, 29, 40, float("inf")]
AGE_LABELS = ["18-20", "21-25", "26-29", "30-40", ">40"]
```
Formula: `pd.cut(age, bins=AGE_BINS, labels=AGE_LABELS, right=True, include_lowest=True)`.
*Note:* `>40` is strictly greater than 40, so a `30-40` band was added so that 30–40 is not left out.

### 2.3 Sum-insured USD bands (verbatim from the brief)
```python
SI_BINS  = [0, 5_000] + list(range(6_000, 51_000, 1_000)) + [float("inf")]
SI_LABELS = ["SI<=5k"] + [f"{i}k<SI<={(i+1)}k" for i in range(5, 50)] + [">50k"]
```
Formula: `pd.cut(suminsured_usd, bins=SI_BINS, labels=SI_LABELS, right=True, include_lowest=True)`.

---

## 3. Functions

### `add_vehicle_type(df, col="vehicletypename")`
Returns a copy with `vehicle_type` added (collapsed categories).

### `add_client_age_bin(df, col="age")`
Coerces `age` to numeric, then `pd.cut` into `client_age_bin`.

### `add_suminsured_bin(df, col="suminsured_usd")`
`pd.cut` of the FX-normalised sum insured into `suminsured_usd_bin`.

### `add_segments(df)`
Calls the three functions above and sets `df["franchise"] = df["deductible_type"]` (alias for the deductible dimension).

### `build_segment_key(df)`
Builds one composite label:
```
segment = "age:" + client_age_bin
        + " | veh:" + vehicle_type
        + " | fr:" + franchise
        + " | si:" + suminsured_usd_bin
```
Used for the most granular aggregation (1,264 distinct segments).

---

## 4. Syntax notes
- `pd.cut(..., right=True)` → bands are (a, b]; `include_lowest=True` gives the first band its left edge.
- Every `add_*` function returns a **copy** (`df.copy()`) — they never mutate the input.
- `float("inf")` as the last bin edge catches every value above the highest explicit edge.

## 5. Verification
- [x] `client_age_bin` covers every age without gaps (18-20, 21-25, 26-29, 30-40, >40)
- [x] `vehicle_type` collapses the 7 mapped raw types; residual rare types are kept
- [x] `suminsured_usd_bin` produces the brief's label set
- [x] `segment` is unique per combination; 1,264 distinct values at portfolio level
