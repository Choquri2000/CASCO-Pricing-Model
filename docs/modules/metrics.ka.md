# დოკუმენტაცია — `src/metrics.py`

> 🇬🇧 English version: [metrics.md](metrics.md)

**როლი:** გამოითვალოს ზარალიანობის კოეფიციენტი / პრემიის რეიტი / სიხშირე / სიმძიმე სეგმენტის მიხედვით.
**დამოკიდებულება:** `load_data` ჩარჩო (საშუალოდ `segments`). **გამოიყენება:** `recommend`, `run`.

---

## 1. ძირითადი ფორმულები

| მეტრიკა | ფორმულა | შენიშვნები |
|---|---|---|
| ზარალიანობის კოეფიციენტი | `incurred_claim / earned_premium` | NaN თუ `earned_premium == 0` |
| პოლისის რეიტი | `gross_written_premium / sum_insured` | პორტფელის დონის ფარდობა |
| საშუალო პოლისის რეიტი | `mean( gwp_policy / si_policy )` | პოლისების რეიტების საშუალო (მდგრადი დიდი პოლისების მიმართ) |
| სიხშირე | `n_claims / n_policies` | ზარალები პოლისზე |
| სიმძიმე | `incurred_claim / n_claims` | საშუალო ღირებულება ზარალზე (NaN თუ 0 ზარალი) |

---

## 2. დამხმარე

### `_safe_div(num, den)`
```python
den = den.replace(0, np.nan)
return num / den
```
აბრუნებს `NaN`-ს (არა `inf`) როცა მნიშვნელის ნაცვლად 0 არის — კრძალავს ჩუმ უსასრულობებს.

---

## 3. `aggregate_by(df, group_cols, ...) -> DataFrame`

აგრეგირებს პოლის-დონის ჩარჩოს ერთ რიგად თითოეული სეგმენტის კომბინაციისთვის.

**პარამეტრები**
- `group_cols`: განზომილების სვეტების სია (მაგ. `["client_age_bin"]` ან `["segment"]`).
- `earned_col`, `incurred_col`, `gwp_col`, `si_col`, `claims_col`: სვეტის სახელები (ნაგულისხმევად ჩარჩოს სვეტები).

**აგრეგაცია (pandas `groupby.agg`)**
```
n_policies   = size()
n_claims     = sum(claims_col)
earned_premium     = sum(earned_col)
incurred_claim     = sum(incurred_col)
gross_written_premium = sum(gwp_col)
sum_insured         = sum(si_col)
```
შემდეგ გამომდინარე:
```
loss_ratio   = _safe_div(incurred_claim, earned_premium)
premium_rate = _safe_div(gross_written_premium, sum_insured)
frequency    = _safe_div(n_claims, n_policies)
severity     = _safe_div(incurred_claim, n_claims)
avg_premium_rate = per-policy (gwp/si) საშუალო   # გამოთვლილი დროებით ასლზე, უკან შერწყმული
```
ყველა ფარდობითი სვეტი 4 ათწილადამდე დამრგვალებული.

**სინტაქსის შენიშვნები**
- `groupby(group_cols, observed=True)` — `observed=True` თავიდან აირიდებს გამოუყენებელი კატეგორიული დონეებისთვის რიგების შექმნას.
- პოლისის რეიტი გამოითვლება `tmp.copy()`-ზე, შემდეგ `groupby(group_cols)["_rate"].mean()` და უკან შერწყმულია `group_cols`-ზე (თავიდან აირიდებს მყიფე tuple-ჯგუფირებას).

---

## 4. `aggregate_overall(df) -> Series`

ერთრიგიანი პორტფელის შეჯამება:
```
n_policies, n_claims, earned_premium, incurred_claim,
gross_written_premium, sum_insured,
loss_ratio = incurred/earned,
premium_rate = gwp/si,
frequency = n_claims/n_policies,
severity = incurred/n_claims
```
4 ათწილადამდე დამრგვალებული. გამოიყენება პორტფელის დონის ბეჭდვისთვის და `portfolio_overall.csv`-თვის.

---

## 5. მაგალითი (პორტფელი)
```
loss_ratio = 0.706,  premium_rate = 0.0407,
frequency = 0.654,  severity = 1538 GEL
```

## 6. ვერიფიკაცია
- [x] `loss_ratio × earned_premium ≈ incurred_claim` თითოეულ რიგში
- [x] `frequency × severity × n_policies ≈ incurred_claim` (დამრგვალების ფარგლებში)
- [x] `avg_premium_rate` განსხვავდება `premium_rate`-სგან (მოსალოდნელია — პოლისის მიხედვით vs პორტფელის)
- [x] არანაირი `inf` მნიშვნელობა (safe-div მართავს ნულოვან მნიშვნელებს)
