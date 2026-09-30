# Documentation — `src/metrics.py`

> 🇬🇪 ქართული ვერსია: [metrics.ka.md](metrics.ka.md)

**Role:** compute loss ratio / premium rate / frequency / severity by segment.
**Depends on:** the `load_data` frame (usually via `segments`). **Used by:** `recommend`, `run`.

---

## 1. Core formulas

| Metric | Formula | Notes |
|---|---|---|
| Loss ratio | `incurred_claim / earned_premium` | NaN if `earned_premium == 0` |
| Policy rate | `gross_written_premium / sum_insured` | portfolio-level ratio |
| Average policy rate | `mean( gwp_policy / si_policy )` | mean of per-policy rates (robust to large policies) |
| Frequency | `n_claims / n_policies` | claims per policy |
| Severity | `incurred_claim / n_claims` | average cost per claim (NaN if 0 claims) |

---

## 2. Helper

### `_safe_div(num, den)`
```python
den = den.replace(0, np.nan)
return num / den
```
Returns `NaN` (not `inf`) when the denominator is 0 — prevents silent infinities.

---

## 3. `aggregate_by(df, group_cols, ...) -> DataFrame`

Aggregates the policy-level frame into one row per segment combination.

**Parameters**
- `group_cols`: list of dimension columns (e.g. `["client_age_bin"]` or `["segment"]`).
- `earned_col`, `incurred_col`, `gwp_col`, `si_col`, `claims_col`: column names (default to the frame's columns).

**Aggregation (pandas `groupby.agg`)**
```
n_policies   = size()
n_claims     = sum(claims_col)
earned_premium     = sum(earned_col)
incurred_claim     = sum(incurred_col)
gross_written_premium = sum(gwp_col)
sum_insured         = sum(si_col)
```
Then derived:
```
loss_ratio   = _safe_div(incurred_claim, earned_premium)
premium_rate = _safe_div(gross_written_premium, sum_insured)
frequency    = _safe_div(n_claims, n_policies)
severity     = _safe_div(incurred_claim, n_claims)
avg_premium_rate = mean of per-policy (gwp/si)   # computed on a temporary copy, merged back
```
All ratio columns are rounded to 4 decimals.

**Syntax notes**
- `groupby(group_cols, observed=True)` — `observed=True` avoids creating rows for unused categorical levels.
- The policy rate is computed on `tmp.copy()`, then `groupby(group_cols)["_rate"].mean()` and merged back on `group_cols` (avoids brittle tuple grouping).

---

## 4. `aggregate_overall(df) -> Series`

One-row portfolio summary:
```
n_policies, n_claims, earned_premium, incurred_claim,
gross_written_premium, sum_insured,
loss_ratio = incurred/earned,
premium_rate = gwp/si,
frequency = n_claims/n_policies,
severity = incurred/n_claims
```
Rounded to 4 decimals. Used for the portfolio-level printout and for `portfolio_overall.csv`.

---

## 5. Example (portfolio)
```
loss_ratio = 0.706,  premium_rate = 0.0407,
frequency = 0.657,  severity = 1546 GEL
```

## 6. Verification
- [x] `loss_ratio × earned_premium ≈ incurred_claim` in every row
- [x] `frequency × severity × n_policies ≈ incurred_claim` (within rounding)
- [x] `avg_premium_rate` differs from `premium_rate` (expected — per-policy vs portfolio)
- [x] no `inf` values (safe-div handles zero denominators)
