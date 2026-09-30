# Methodology Review — v2 corrections

> 🇬🇪 ქართული ვერსია: [review.ka.md](review.ka.md)

After the original submission ([report](report.md), v1) I reviewed the methodology against the data and found five issues that affected the results. This page documents each one, the fix, and its measured impact. **All "v2" figures below come from the current code** (`python -m src.run`, `python -m src.experiments`, and the Part B modules).

**What did not change:** the portfolio loss ratio (70.6%) and the main business findings — young drivers, no-deductible policies, low sum-insured vehicles and sedans are where the book is under-priced.

---

## Summary

| # | Issue | Fix | Key impact |
|---|---|---|---|
| 1 | The Gini metric rewarded policy *size*, not risk | Exposure-weighted Gini on the predicted rate, plus a "current premium" baseline | Model quality is now measured honestly (see §1) |
| 2 | Earned premium (GEL) was used as the exposure | Earned policy-years from the policy dates | Models no longer contain the current price they are judging |
| 3 | LogNormal severity predicted the *median*, not the mean | Duan smearing factor | Calibration factor 1.68 → 0.95 |
| 4 | Legal entities were not filtered out | Inner join on physical clients | 4,629 policies removed (119,745 → 115,116) |
| 5 | 95% of Part A segments said "Hold" | Square-root credibility on claim counts, complement = portfolio indication | 238 segments to load above the book, 90 below |

---

## 1. The Gini metric measured size, not risk

**Problem.** The Gini was computed on raw claim counts/amounts. Bigger or longer policies have bigger losses, so any predictor correlated with size scores well. In v1, the **current premium alone** scored 0.396 on pure premium — almost the same as the best model (0.409). Under that metric even "years on risk" alone scores 0.254 (EXP 9).

**Fix.** `frequency.gini_normalized`: policies are sorted by the predicted **rate** (prediction ÷ exposure), and the Lorenz curve is weighted by exposure. A predictor that is just proportional to exposure scores exactly 0. Every model table now also shows the **current premium as a baseline**.

| Out-of-time Gini (test set) | v1 metric | v2 metric |
|---|---|---|
| Frequency — Poisson GLM | 0.391 | **0.201** |
| Frequency — LightGBM | 0.409 | **0.235** |
| Frequency — current premium (baseline) | — | 0.109 |
| Pure premium — Freq × Sev (GLM) | 0.409 | **0.300** |
| Pure premium — Tweedie GBM | 0.356 | 0.290 |
| Pure premium — current premium (baseline) | — | 0.303 |
| Hold-out: predicted loss ratio (premium-weighted) | 0.129 | **0.159** |

**What this means:**
- The models rank **claim frequency** about twice as well as the current tariff (0.235 vs 0.109).
- On **total claim cost**, the models only match the tariff (0.300 vs 0.303). The tariff already orders cost well through the sum insured.
- The models' real value is finding **mispriced policies**: the predicted loss ratio ranks actual loss ratios with a Gini of 0.159 on the hold-out. The segment/credibility approach reaches 0.124.

## 2. Earned premium was used as the exposure

**Problem.** `earned_premium` equals written premium × the fraction of the term elapsed (correlation 1.0 in the data). Using it as the GLM offset means modelling "claims per GEL of current premium", which builds the tariff being evaluated into the model.

**Fix.** `load_data` now computes `earned_years`: time on risk from the start date to the earliest of expiry, cancellation and the extraction date (2026-05-15). That gives 91,888 policy-years, with 113 policies having no time on risk yet. The GLMs use `offset = log(earned_years)`. The LightGBM models get the same offset through `init_score`, which trees cannot otherwise use:

| Frequency GBM exposure handling (EXP 5) | Gini | Predicted / actual claims |
|---|---|---|
| `init_score` offset (production) | **0.235** | 0.98 |
| log(exposure) as a feature | 0.213 | 0.98 |
| no exposure information | 0.169 | 1.56 |

## 3. LogNormal severity predicted the median

**Problem.** The severity model fits `log(amount)`; `exp(prediction)` is the **median** of a lognormal, not its mean. Every claim was under-predicted by the same factor, which the "calibration factor" of 1.68 was silently absorbing.

**Fix.** Duan's smearing factor `mean(exp(residual))` = **1.78** on this data (`severity.fit_lognormal` / `predict_lognormal`).

| | v1 | v2 |
|---|---|---|
| Portfolio calibration factor | 1.68 | **0.95** |
| LogNormal mean prediction ÷ actual (test) | ~0.59 | **1.06** |

**Rate indication (Part B, 65% target, test set):**

| | v1 | v2 |
|---|---|---|
| Mean indicated rate change | +18.5% | **+8.3%** |
| Mean expected volume change (elasticity −0.5) | −9.3% | −4.2% |
| Policies to increase / decrease (±5%) | 22,505 / 5,735 | 17,053 / 10,104 |
| Hold-out actual vs predicted loss ratio | 0.823 vs 0.784¹ | **0.668 vs 0.647** |

¹ v1 averaged per-policy loss ratios; v2 uses ratios of sums (total claims ÷ total premium), the standard definition. The monthly monitoring table was fixed the same way.

The hold-out period's loss ratio (66.8%) is close to the 65% target, so the model-based indication is smaller than the Part A portfolio figure. The most recent months are also immature — claims are still being reported (April–May 2026 actual/predicted ratios are 0.56 and 0.43) — so the true hold-out loss ratio is likely somewhat higher.

## 4. Legal entities were not filtered out

**Problem.** The brief needs physical persons only, but client attributes were *left*-joined, so policies of legal entities stayed in the data with an empty age. The corresponding test had been weakened to allow this.

**Fix.** Inner join on physical clients; the test now checks that every policy belongs to a physical client.

| | v1 | v2 |
|---|---|---|
| Policies | 119,745 | **115,116** (−4,602 legal entities, −27 unknown) |
| Earned premium | GEL 172.4M | GEL 163.9M |
| Incurred claims | GEL 121.7M | GEL 115.7M |
| Portfolio loss ratio | 70.6% | 70.6% |
| Composite segments | 1,264 | 1,056 (the removed policies formed separate "age: unknown" segments) |

## 5. Part A: 95% of segments said "Hold"

**Problem.** Credibility was `min(1, earned premium / GEL 5M)`, so the median segment had Z = 0.003. The complement of credibility was "no change", so thin segments were told to hold even though the whole book is 17.7% under-priced. Result: 1,205 of 1,262 segments on "Hold".

**Fix.** Classical limited-fluctuation credibility on the segment's **claim count**, `Z = min(1, √(n_claims / 1,082))` (1,082 claims = within 5% with 90% probability). The complement is the **portfolio-wide indication** (70.6% / 60% − 1 = +17.7%):

```
recommended = Z × (segment LR / target − 1) + (1 − Z) × (portfolio LR / target − 1)
```

A new column, `relative_to_portfolio`, shows each segment's change relative to the book-wide move, which tells underwriters *where* to load more or less.

| Part A (1,056 segments) | v1 | v2 |
|---|---|---|
| Median credibility | 0.003 | 0.068 |
| Actions | Hold 1,205 · Increase 50 · Decrease 7 | Increase 1,044 · Hold 8 · Decrease 4 |
| Load more than the book (> +5% relative) | — | **238** |
| Load less than the book (< −5% relative) | — | **90** |

**One-way indications (v2):**

| Factor | Loss ratio | Recommended change | Relative to book |
|---|---|---|---|
| Age 21–25 | 86.7% | +44.5% | +22.8% |
| Age 26–29 | 88.9% | +48.1% | +25.8% |
| Age 30–40 | 81.3% | +35.5% | +15.1% |
| Age >40 | 63.0% | +5.1% | −10.7% |
| Sedan | 77.7% | +29.5% | +10.0% |
| Off-road / SUV | 67.4% | +12.4% | −4.5% |
| Coupe / convertible | 46.6% | −13.7% | −26.7% |
| No deductible | 74.4% | +24.0% | +5.3% |
| With deductible | 54.9% | −8.5% | −22.3% |

---

## Engineering changes

- **Tests:** 48 → **53** (new: physical-client filter, exposure bounds, exposure-invariant Gini, GBM offset round-trip, smearing, credibility complement). The data is now loaded once per test run instead of once per test.
- **Synthetic data:** `scripts/make_synthetic_data.py` simulates a portfolio with the same schema, so the tests and pipelines run without the confidential files (`CASCO_DATA_DIR=data/synthetic`).
- **CI:** GitHub Actions runs the full suite on the synthetic data on every push.
- **Experiments:** EXP 5 and EXP 7 were rewritten for the new exposure and smearing; EXP 9 (raw vs weighted Gini) was added.

## Still open

- Immature recent months are not developed (no IBNR / chain-ladder adjustment).
- Target loss ratios differ between Part A (60%) and Part B (65%) — both are management assumptions.
- Elasticity (−0.5) is assumed, not estimated.
