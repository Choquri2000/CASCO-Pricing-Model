# CASCO Claims-Cost & Underwriting Pricing Model
### TBC Insurance — Technical Task · End-to-End Project Presentation

> 🇬🇪 ქართული ვერსია: [presentation.ka.md](presentation.ka.md) · PDF: [presentation.pdf](presentation.pdf)

> ℹ️ **Original submission (v1).** For the corrected methodology and current results see the [methodology review](../review.md).

**Domain:** Motor (CASCO) insurance · **Two parts:** A — Segment rating · B — Advanced GLMs/GBM
**Tests:** 48 tests · 11 modules · 0 failures · **Languages:** English + Georgian (KA)

---

## Agenda
1. Business problem & objectives
2. Data sources & schema
3. Solution architecture (pipeline)
4. Part A — Segment experience-rating
5. Part B — Advanced statistical models
6. Key modelling decisions & "why"
7. Engineering strength: tests, EDA, experiments
8. What we tested (full matrix)
9. Results, findings & insights
10. Conclusion & next steps

---

## 1 · Business Problem & Objectives
CASCO is comprehensive motor insurance. The book is **under-priced**: portfolio loss ratio is
**70.6%** against a **60%** management target — roughly an **18% average under-pricing**.

> **Loss Ratio (LR)** = Incurred Claims ÷ Earned Premium.
> **Pure premium** estimates `E[cost] = E[N] · E[S]` where `N` = claim count (frequency) and
> `S` = claim amount (severity). **Technical premium** = `model_pp / target_LR`.

| Objective | What we deliver |
|---|---|
| **Diagnose** | Segment the book on 4 rating dimensions; surface hot/cold segments driving 70.6%. |
| **Indicate** | Credibility-weighted, capped (±50%) rate corrections vs. target loss ratio. |
| **Model** | Individual-risk frequency × severity models, validated **out-of-time**, with rate indication + elasticity. |

---

## 2 · Data Sources & Schema
All raw inputs live in `data/`; a single trusted cleaning/join layer (`src/load_data.py`) produces
one analysis-ready policy-level frame.

| File | Role | Key content |
|---|---|---|
| `Policies_1805_v4.csv` | Policy master | premium, sum insured, vehicle, driver age, effective date, deductible |
| `Claims_1805_v2.csv` | Claims | claim amounts, dates, linked policy |
| `Clients_1805_v3.csv` | Client master | client type (physical/legal), personal-use flag |
| `enrcols.csv` | Enrichment | deductible category, eligible driver count, min driver age, car age |
| `franchise_field_categories.csv` | Lookup | deductible category mapping |
| `fx_rates.csv` | FX | currency → GEL (USD sum-insured → GEL) |

**Cleaning rules:** keep CASCO + physical + personal-use; validate claims; convert sum-insured to
GEL; compute `earned_premium`; aggregate claims per policy (zeros filled); compute `loss_ratio` only
where `earned_premium > 0` (safe divide → NaN); derive `exposure = earned_premium.clip(lower=0)`
(GLM offset / GBM weight); enrich with `deductible_type`, `eligible_driver_count`, `min_driver_age`,
`carage`.

> This single layer is the only place raw data is touched — every downstream module consumes the
> same clean frame, so changes cascade predictably.

---

## 3 · Solution Architecture
Two cooperating parts share the cleaned frame. Part A = fast, explainable segment view; Part B =
individual-risk models validated out-of-time.

**Part A — Segment experience-rating (`run.py` orchestrates):**
`load_data` → `segments` → `metrics` → `recommend` → `run` (CSV + Excel)

**Part B — Advanced individual-risk models:**
`features` → `frequency` → `severity` → `pure_premium` → `credibility` → `pricing` → `validation`

- **Time-based split:** train `efdate < 2025-01-01`, test `efdate ≥ 2025-01-01` (avoids leakage).
- **Exposure as offset:** `offset = log(exposure)` where `exposure = earned_premium`; re-applied at predict.
- **Outputs:** 1,264 segments, portfolio summary, 6 breakdown sheets, model metrics & monitoring tables.

---

## 4 · Part A — Segment Experience-Rating

**Segmentation (`segments.py`)** — four rating dimensions, collapsed for stability:
- **Age:** 18–20 · 21–25 · 26–29 · 30–40 · >40
- **Vehicle type:** SUV-type · Sedan · Coupé/Cabrio (collapsed to 3)
- **Deductible:** Yes / No
- **Sum insured:** USD bands from the brief (≤5k · 1k-wide bands 5k–50k · >50k)

→ **1,264** composed segments.

**Metrics (`metrics.py`):** `aggregate_by` computes per-segment LR/rate/frequency/severity;
`safe_div` returns NaN (not inf) on zero exposure; `aggregate_overall` gives portfolio totals.

**Recommendations (`recommend.py`):** correction = credibility-weighted experience vs.
`target_loss_ratio = 0.60`; capped ±50%; thin segments shrink toward the mean via credibility `Z`;
action label (increase/decrease/hold) attached.

> All corrections are point estimates that ignore elasticity — a documented limitation.

---

## 5 · Part B — Advanced Statistical Models

- **Frequency (`frequency.py`):** Poisson & NegBin GLM with `offset = log(exposure)`; LightGBM
  Poisson GBM using `log_exposure` as a feature; NegBin started from Poisson MLE with `alpha=0.1`
  (never 0 → avoids `log(0)` BFGS blow-up); **offset re-applied at predict**.
- **Severity (`severity.py`):** models amount per claim; LogNormal GLM + LightGBM Gamma GBM;
  **Gamma GLM dropped** (IRLS/BFGS diverges on heavy tail).
- **Pure premium (`pure_premium.py`):** `E[cost]=E[N]·E[S]` — multiplicative Poisson×LogNormal **and**
  direct Tweedie (power 1.5) on `incurred_claim`; `calibration_factor = mean(actual $)/mean(predicted $)`.
- **Credibility (`credibility.py`):** Bühlmann-Straub `Z_i = n_i/(n_i+k)`, `k=EPV/VPP`; `n_i` =
  **policy count** (not dollar exposure); shrinks observed PP toward portfolio mean.
- **Pricing (`pricing.py`):** technical premium = `model_pp / target_LR` (0.65 in Part B); rate change
  capped ±50%; elasticity-based volume response (−0.5); calibration factor applied pre-indication.
- **Validation (`validation.py`):** monthly actual-vs-predicted LR monitoring on hold-out; out-of-time
  insurance Gini; level-calibration check (ratio ≈ 1.0).

---

## 6 · Key Modelling Decisions & "Why"

| Decision | Why |
|---|---|
| Time-based split (not random) | Random split leaks future policies into training and inflates Gini. |
| `offset = log(earned_premium)` | Standardises to one unit of exposure; re-applied at predict or model predicts rate×exposure, not expected count. |
| Drop Gamma GLM for severity | IRLS/BFGS diverges on heavy tail; LogNormal GLM + Gamma GBM are stable. |
| Multiplicative freq×sev **and** Tweedie | Decomposes cost driver + cross-check; Tweedie models zero-inflated claims natively. |
| Credibility uses **policy count** n | Dollar exposure would make every segment "fully credible"; count reflects real volume. |
| ±50% cap + credibility | Prevents thin segments from destabilising extreme corrections. |
| Calibration factor before indication | Multiplicative model under-predicts average PP (factor ≈ 1.68); corrects level, not shape. |
| Two target LRs (0.60 / 0.65) | Separate management parameters; both set before deployment. |

---

## 7 · Engineering Strength — Tests, EDA, Experiments
A model you cannot repeat or defend is not shippable.

- **Tests (`tests/`):** **48 tests · 11 modules · 0 failures.** Each file documents *why* it exists;
  the suite already caught a NegBin `alpha=0` divergence (20-min lock-up) and an experiments
  `KeyError: 'segment'`.
- **EDA (`src/eda.py`):** 9-step function (overview, frequency, severity, exposure, segments, time
  trend, feature relationships, zero-claim deep-dive, credibility preview) — each *shows* the facts.
- **Experiments (`src/experiments.py`):** 8 what-if probes that *prove* each choice: Gamma GLM
  divergence (EXP 2), `log_exposure` ablation (EXP 5), policy-count vs dollar credibility (EXP 6),
  calibration flipping the indication sign (EXP 7), NegBin vs Poisson (EXP 8).

> **Process rule:** any change in `load_data.py`, a model, or a metric is "ready" only when
> `python -m tests.run_all` is green and `python -m src.experiments` still completes.

---

## 8 · What We Tested — Full Matrix

| Module | # Tests | Asserts |
|---|---|---|
| `test_load_data` | 8 | policy-level & non-empty; CASCO-only; physical; personal-use; positive finite SI; claims aggregated w/ zeros; deductible yes/no; LR only where earned>0 |
| `test_segments` | 5 | 4 dims present; age bins gap-free; franchise binary; vehicle collapsed to 3+; key unique per combo |
| `test_metrics` | 4 | safe_div → NaN not inf; core metrics present; internally consistent; known portfolio LR |
| `test_recommend` | 5 | corrections within cap; credibility in [0,1]; shrinks thin segments; hot segment +correction; action label consistent |
| `test_features` | 5 | time split no overlap & respects cutoff; y_sev only where claim; feature engineering; matrix shapes; exposure non-negative |
| `test_frequency` | 4 | Poisson deviance ≥ 0; offset re-applied at predict; train/evaluate runs & discriminates |
| `test_severity` | 4 | Gini of constant = 0; Gamma deviance ≥ 0; training target no zeros; train/evaluate runs & discriminates |
| `test_pure_premium` | 4 | Tweedie deviance ≥ 0; calibration factor sensible; predict aligned to exposed rows; discriminates |
| `test_credibility` | 3 | Z in [0,1] & k>0; mean Z shows real shrinkage; blended Gini beats raw out-of-time |
| `test_pricing` | 3 | rate change capped; volume = elasticity × rate change; calibrated indication positive on avg |
| `test_validation` | 3 | monitoring report shape & columns; holdout Gini > 0; level calibration ≈ 1 |
| **Total** | **48** | **11 modules · 0 failures** |

---

## 9 · Results, Findings & Insights

**Portfolio (Part A):** LR **70.6%** (vs 60% target) · **119,745** policies · Earned premium
**GEL 172.4M** · Incurred **GEL 121.7M**.

**Model discrimination (out-of-time, Part B):**

| Model | Gini | Note |
|---|---|---|
| Frequency — Poisson GLM | 0.3909 | baseline GLM |
| Frequency — LightGBM (Poisson) | 0.4085 | beats GLMs |
| Severity — LogNormal GLM | 0.2664 | interpretable base |
| Pure premium — Freq×Sev (GLM) | 0.4086 | strongest ranker |
| Pure premium — Tweedie GBM | 0.3555 | competitive on deviance |
| Credibility — blended | 0.0805 | vs raw 0.0678 (improvement) |

**Key insights:**
- **Young drivers (21–29)** worst on LR *and* already pay highest per-policy rate (~2× >40) — book still loses money on them.
- **No-deductible policies** ~19 pts worse (0.743 vs 0.555) at the *same* average rate — deductible not priced.
- **Low sum-insured cars** most under-priced; rate curve is inverse to risk.
- **Test calibration:** actual LR 0.8225 vs predicted 0.7838 (target 0.65) → well-calibrated in *level* (≈1.05); book ~17–22% above target.
- Avg indicated rate change **+18.5%**; volume **−9.3%**; 22,505 policies ↑, 5,735 ↓.

---

## 10 · Conclusion & Next Steps

**Delivered:** explainable segment rating (1,264 segments) + model-based individual-risk pricing;
out-of-time validated with full test/EDA/experiment harness; complete Georgian translation reviewed
and verified (0 test failures).

**Next steps:**
1. Set management target loss ratios (cost + profit load) before deployment.
2. Calibrate full-credibility standard to portfolio volatility.
3. Validate corrections on a hold-out; simulate premium/LR response.
4. Deploy `validation.py` monitoring dashboard; back-test indication vs realised LR.
5. Consider GLMM / boosted hybrid and a proper Tweedie power search.

> **Bottom line:** the book is under-priced by ~18%; the model explains *where* (young drivers,
> no-deductible, low sum-insured) and indicates risk-adequate, credibility-capped corrections —
> reproducible, tested, and documented in both English and Georgian.

---
*CASCO Claims-Cost & Underwriting Model — Project Presentation · Tests: 48 · 11 modules · 0 failures · EN + KA*
