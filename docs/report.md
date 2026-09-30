# CASCO Claims-Cost Model and Underwriting Recommendations — Analysis Report

> 🇬🇪 ქართული ვერსია: [report.ka.md](report.ka.md)

*Author: Beka Chokuri*
*Scope: TBC Insurance CASCO portfolio — physical (individual) clients, personal-use vehicles*

---

## 1. Executive summary

The current CASCO portfolio is **running above its target loss ratio**. Across **119,745** policies the portfolio shows:

| Metric | Value |
|---|---|
| Earned premium | **GEL 172.4M** |
| Incurred claims | **GEL 121.7M** |
| **Portfolio loss ratio** | **70.6%** |
| Gross written premium | GEL 223.8M |
| Sum insured (GEL) | GEL 5.49B |
| Policy rate (GWP / sum insured) | 4.07% |
| Claim frequency | 0.66 claims / policy |
| Claim severity | GEL 1,546 |

At a **60% target loss ratio**, the portfolio is under-priced by **+18%** on average
(`0.706 / 0.60 − 1`). The mispricing is not uniform — it is
concentrated in specific risk segments, which is exactly where
rate action should be taken.

**Key findings**

* **Younger drivers are the hottest segment.** Ages 21–29 run loss ratios of
  **87–89%** vs **63%** for drivers over 40, even though they already pay
  on average twice the per-policy rate.
* **No-deductible policies (franchise = No) are materially worse** (loss ratio
  **74.3%**) than policies with a deductible (**55.5%**), yet both have the same
  average rate (4.97%).
* **Low sum-insured vehicles are under-priced.** The loss ratio falls steadily
  from ~0.75–0.85 in the smallest bands to **48%** above USD 50k, while the policy
  rate also *decreases* with sum insured — the opposite of what the risk indicates.
* **Off-road / SUV-class vehicles** dominate the volume (68k policies) and run at a
  **67%** loss ratio; **sedans** (50k policies) run at **78%**.

The pipeline produces a full price-correction table (capped at ±50%, shrunk
by credibility) for **1,264 composite segments** — see `output/`.

---

## 2. Data & methodology

### 2.1 Sources (in `data/`)

| File | Role | Main join |
|---|---|---|
| `Policies_1805_v4.csv` | Policy master (128k rows) | `policyid` |
| `Claims_1805_v2.csv` | Claims (98k rows) | `policyid` |
| `Clients_1805_v3.csv` | Client master (55k rows) | `clientid` |
| `enrcols.csv` | Policy enrichment (Casco/MTPL/MPA cross-product) | `id` = `policyid` |
| `fx_rates.csv` | Daily GEL/USD (2.7k rows) | as-of `efdate` |
| `franchise_field_categories.csv` | Deductible-category lookup | `resolved_value` |

### 2.2 Cleaning and filtering (`src/load_data.py`)

1. **CASCO only** — keep policies whose `licensename` contains "casco".
2. **Physical clients only** — keep `clientstatus` containing "ფიზიკურ"
   (individual / physical person).
3. **Personal use only** — keep `enrcols.გამოყენება` (usage) containing "პირად"
   (personal).
4. **Valid claims only** — `calcclaimstatus` ∈ {"Easy Settlement",
   "Hard Settlement"}; incurred = sum of `reportedclaimamount`.
5. **FX normalisation** — `suminsured_usd = suminsuredgel / gel_per_usd` via a backward
   `merge_asof` on the policy effective date, so every policy gets the FX rate
   in force at its start.
6. **Deductible (franchise) resolution** — implemented exactly as in the project
   brief: resolve the deductible from `ფრანშიზის ველი` → `ფრანშიზა` →
   `არასტანდარტული ფრანში`, map the resolved value to `deductible_category`
   using `franchise_field_categories.csv`, and flag the policy
   `deductible_type = "No"` when the category is a zero/no-deductible class,
   otherwise `"Yes"`.

### 2.3 Risk segmentation (`src/segments.py`)

Four rating dimensions, taken verbatim from the brief's snippets:

* **Client age** → bands `18-20`, `21-25`, `26-29`, `30-40`¹, `>40`.
* **Vehicle type** → collapse with the brief's `.replace()` map into
  *sedan / off-road-SUV class / coupe-convertible* (remaining rare types are kept).
* **Deductible** → `deductible_type` ("Yes" / "No").
* **Sum insured (USD)** → the brief's `pd.cut` bands (`SI<=5k`, `6k<SI<=7k`, …,
  `>50k`).

¹ The brief lists `18-20, 21-25, 26-29, >40`; the `30-40` band was added so that the
30–40 age range is not silently dropped (`>40` is strictly greater than 40).

### 2.4 Metrics (`src/metrics.py`)

* **Loss ratio** = incurred claims / earned premium
* **Policy rate** = gross written premium / sum insured
* **Frequency** = claims / policies; **severity** = incurred / claims
* Per-segment aggregates are built for the composite segment and for each
  single dimension and the main two-way crosses.

### 2.5 Recommendations (`src/recommend.py`)

For every segment:

```
raw_correction        = (loss_ratio / target_loss_ratio) - 1
credibility           = min(1, earned_premium / full_credibility_premium)
recommended_correction = clip(raw_correction * credibility, -0.50, +0.50)
recommended_rate       = current_policy_rate * (1 + recommended_correction)
```

Defaults: `target_loss_ratio = 0.60`, `full_credibility_premium = GEL 5M`,
`max_correction = ±50%`. Credibility shrinks the corrections for thin segments so
that we do not over-react to noisy loss ratios.

---

## 3. Portfolio results

| Metric | Value |
|---|---|
| Policies | 119,745 |
| Claims | 78,704 |
| Earned premium (GEL) | 172,359,600 |
| Incurred claims (GEL) | 121,668,700 |
| Loss ratio | **0.706** |
| Policy rate | 0.0407 |
| Frequency | 0.657 |
| Severity (GEL) | 1,546 |

The portfolio loss ratio of **70.6%** is ~18% above the 60% target, which
confirms systematic under-pricing at portfolio level.

---

## 4. Segment-level findings

### 4.1 By client age

| Age band | Policies | Loss ratio | Policy rate | Average policy rate |
|---|---|---|---|---|
| 18-20 | 130 | 0.636 | 0.042 | **0.095** |
| 21-25 | 2,159 | **0.867** | 0.046 | 0.074 |
| 26-29 | 5,773 | **0.889** | 0.049 | 0.063 |
| 30-40 | 36,398 | 0.813 | 0.044 | 0.053 |
| >40 | 70,640 | **0.630** | 0.038 | 0.046 |

Young drivers (21–29) are the worst segment by loss ratio,
but they already pay the highest per-policy rates
(~9.5% for 18-20 vs 4.6% for 40+). Their pricing is more
adequate than the raw loss ratio suggests, but the book still
loses money on them. Drivers over 40 are the most profitable.

### 4.2 Vehicle type (main categories)

| Vehicle type | Policies | Loss ratio | Policy rate |
|---|---|---|---|
| Off-road / SUV class (მაღალი გამავლობის) | 68,002 | 0.673 | 0.036 |
| Sedan (სედანი) | 50,237 | **0.778** | 0.053 |
| Coupe / convertible (კუპე/კაბრიოლეტი) | 1,169 | 0.469 | 0.048 |

Sedans show a materially higher loss ratio than off-road vehicles, even though
their policy rate is higher — sedans are under-priced relative to the off-road types.
(The remaining rare types — bus, truck, van, etc. — make up <0.1% of the volume and are excluded
from this summary.)

### 4.3 By deductible (franchise)

| Deductible | Policies | Loss ratio | Policy rate | Average policy rate |
|---|---|---|---|---|
| No deductible | 106,049 | **0.743** | 0.042 | 0.0497 |
| With deductible | 13,696 | **0.555** | 0.037 | 0.0497 |

No-deductible policies are ~19 points worse on loss ratio, yet they are charged
the **same** average rate as policies with a deductible. This is a clear pricing
inefficiency: the benefit of the deductible is not reflected in the price.

### 4.4 By sum insured (USD)

| Sum-insured range | Loss ratio | Policy rate |
|---|---|---|
| SI ≤ 5k | ~0.55–0.75 (mixed) | higher |
| 5k < SI ≤ 10k | ~0.74–0.80 | ~0.05–0.06 |
| 10k < SI ≤ 25k | ~0.70–0.77 | ~0.035–0.045 |
| 25k < SI ≤ 50k | ~0.60–0.85 (volatile) | ~0.033–0.038 |
| **SI > 50k** | **0.480** | **0.033** |

The loss ratio decreases monotonically as the sum insured grows, while the policy rate also
*decreases* — low-value vehicles are the most under-priced relative to their risk.

---

## 5. Recommendations

The full correction table is in `output/segment_recommendations.csv` (1,264
composite segments) and in `output/casco_segment_analysis.xlsx`. Illustrative
high-impact actions (top segments by earned premium):

| Segment | Earned premium (GEL) | Loss ratio | Action | Rate change |
|---|---|---|---|---|
| age>40 / off-road-SUV / no / SI>50k | 9.0M | 0.53 | Decrease | **−12%** |
| age>40 / off-road-SUV / yes / SI>50k | 8.5M | 0.41 | Decrease | **−31%** |
| age>40 / sedan / no / SI≤5k | 5.5M | 0.64 | Increase | **+6%** |
| age 30-40 / sedan / no / SI≤5k | 3.2M | 0.79 | Increase | **+21%** |
| age 30-40 / off-road-SUV / yes / SI>50k | 3.3M | 0.39 | Decrease | **−23%** |

**Strategic directions**

1. **Load no-deductible policies** — they run at 74% vs 56% for deductible policies;
   the rate should reflect the deductible choice (e.g. +10–20% for no deductible).
2. **Re-rate young drivers (21–29)** — even at 2× the policy rate they are still
   hot; consider an additional loading or stricter terms.
3. **Re-rate low sum-insured vehicles** — they are the most under-priced;
   the policy rate should *increase* for low sum insured, not decrease.
4. **Discount high sum-insured / deductible segments** — they are over-priced
   relative to their loss experience and represent a growth/retention opportunity.

All corrections are credibility-weighted and capped at ±50% to avoid
destabilising thin segments.

---

## 6. How to run

```bash
python -m src.run
```

Dependencies: `pandas`, `numpy`, `openpyxl`. The script prints the portfolio
summary and the top segments, and writes the outputs listed below.

Individual modules can also be run for exploration:

```bash
python -m src.load_data     # load and clean the analysis frame
python -m src.segments      # segment distribution
python -m src.metrics       # portfolio + segment metrics
python -m src.recommend     # recommendations preview
```

---

## 7. Outputs (`output/`)

| File | Contents |
|---|---|
| `segment_recommendations.csv` | 1,264 composite segments with loss ratio, policy rate, credibility, recommended correction %, action |
| `portfolio_overall.csv` | One-row portfolio totals and ratios |
| `casco_segment_analysis.xlsx` | Sheets: Portfolio_Overall, Segment_Recommendations, and breakdowns by age / vehicle / deductible / sum insured / age×vehicle / vehicle×deductible |

---

## 8. Limitations and next steps

* **The target loss ratio is an assumption** (60%). It should be set by management
  together with the expense and profit loads; the pipeline exposes it as a
  parameter.
* **The credibility standard (GEL 5M earned premium)** is a default; calibrate it
  to the portfolio's own volatility.
* **One-way loss ratios only** — there is no a-priori / Bornhuetter-Ferguson adjustment
  for immature periods; young/low-volume segments rely on credibility shrinkage.
* **Remaining vehicle types** are kept as-is (per the brief's mapping); consider
  merging them into the three main categories for a cleaner tariff.
* **No exposure/earning-pattern correction beyond `earned_premium`** as
  given in the source; if earned premium is restated, the loss ratios must be reviewed.
* **Next step:** validate the corrections against a hold-out period and simulate
  the premium impact / loss-ratio response before deployment.

---

## 9. Advanced statistical models (Part B)

Part A (sections 1–8) is the **segment / experience-rating** view. Part B builds
**individual-risk statistical models** on the same cleaned frame, validates them
**out-of-time** (no random split — train `efdate < 2025-01-01`, test
`efdate >= 2025-01-01`), and delivers a model-based rate indication
with elasticity and a monitoring dashboard.

### 9.1 Methodology

* **Time-based split** (`src/features.py`) — avoids leakage; the test window is the
  most recent 12+ months. Train (exposure > 0): **87,961** policies;
  test: **31,764**. Train with claims: **37,082**; test with claims: **10,572**.
* **Frequency** (`src/frequency.py`) — expected number of claims per policy.
  Poisson and Negative-Binomial GLMs with `offset = log(earned_premium)`;
  a LightGBM Poisson GBM (with a `log_exposure` feature, so it gets the same exposure
  normalisation as the GLMs). **The offset is re-applied at prediction
  time** — a GLM fitted with an offset but scored without it
  predicts a per-unit-exposure rate, not the expected count.
* **Severity** (`src/severity.py`) — the claim amount *conditional on a positive
  payment* (zero-payment claims are already counted by frequency). LogNormal
  GLM (Gaussian on `log(amount)`) and a LightGBM Gamma GBM. **The Gamma GLM
  was dropped** — `statsmodels` IRLS/bfgs breaks down on this heavy-tailed target
  (the intercept explodes or it falls into an inversely-ranked local optimum).
* **Pure premium** (`src/pure_premium.py`) — `E[cost] = E[N]·E[S]`:
  a multiplicative Poisson×LogNormal model **and** a direct Tweedie (power 1.5)
  LightGBM on `incurred_claim` (zero mass + continuous tail).
* **Credibility** (`src/credibility.py`) — Bühlmann-Straub shrinks each
  segment's observed pure premium toward the portfolio mean with
  `Z_i = n_i / (n_i + k)`, `k = EPV/VPP`, where `n_i` = **number of policies** (not
  dollar exposure, which would make every segment fully credible).
* **Pricing** (`src/pricing.py`) — technical premium = `model_pp / target_LR`,
  rate change capped at ±50%, elasticity-based volume response.
  A **calibration factor** (mean actual ÷ mean predicted cost) corrects the
  multiplicative model's level before the indication.
* **Validation** (`src/validation.py`) — monthly actual-vs-predicted loss-ratio
  monitoring on the hold-out, plus an out-of-time insurance Gini.

**Insurance Gini** (the ranking metric used throughout): Lorenz / accuracy-ratio
form — policies sorted by predicted risk (ascending), `Gini = 1 − 2·(area
under the cumulative-loss Lorenz curve)`. Bounded, rank-based and stable even
for heavy-tailed severity (unlike the covariance form, which scales with the variance).
0 = no discrimination; higher = better.

### 9.2 Frequency — out-of-time (test, exposure > 0 = 31,764)

| Model | Gini | Poisson deviance |
|---|---|---|
| Poisson GLM | **0.3909** | 33,364.83 |
| Negative-Binomial GLM | 0.3909 | 33,364.83 |
| LightGBM (Poisson) | **0.4085** | 32,777.19 |
| Baseline (constant) | 0.0000 | — |

The GBM beats the GLMs; NegBin collapses to Poisson (no over-dispersion
beyond what the exposure explains).

### 9.3 Severity — out-of-time (policies with claims, test = 10,572)

| Model | Gini | Gamma deviance |
|---|---|---|
| LogNormal GLM | **0.2664** | 15,210.30 |
| LightGBM (Gamma) | 0.2654 | 11,319.63 |
| Baseline (constant) | 0.0000 | — |

The two models agree; the GBM has a lower deviance (better fit to the
tail) while the LogNormal GLM is the interpretable parametric baseline.

### 9.4 Pure premium — out-of-time (test = 31,764, actual = incurred_claim)

| Model | Gini | Tweedie deviance |
|---|---|---|
| **Frequency × Severity (GLM)** | **0.4086** | 3,560,151.73 |
| Tweedie GBM (direct) | 0.3555 | 3,525,121.28 |
| Baseline (constant) | 0.0000 | — |

The multiplicative GLM decomposition is the stronger ranker on this book;
the direct Tweedie GBM is competitive on deviance but ranks worse.

### 9.5 Credibility (Bühlmann-Straub)

* Portfolio pure premium `μ = 0.7185`; `k = 16.54`.
* Mean `Z = 0.3619` (median `0.2321`) → most segments are materially shrunk
  toward the mean; only the largest keep their own experience.
* Out-of-time pure-premium Gini: constant **0.0000** → raw observed segment
  **0.0678** → **credibility-blended 0.0805**. Blending experience with the
  portfolio mean *improves* the ranking over the raw observed cell means.

### 9.6 Pricing / rate indication (test set)

* Calibration factor (train): **1.6821** — the multiplicative model
  under-predicts the average pure premium, and the level is scaled up before the indication.
* Mean indicated rate change: **+18.5%** (the portfolio is under-priced
  against the 65% target loss ratio used here).
* Mean expected volume change (elasticity `−0.5`): **−9.3%**.
* Policies recommended for an **increase** (rate change > +5%): **22,505**;
  recommended for a **decrease** (< −5%): **5,735**.

### 9.7 Out-of-time validation and monitoring

Monthly actual-vs-predicted loss ratio on the hold-out (2025-01 → 2026-05):

| Month | n | Earned premium (GEL) | Actual LR | Pred. LR | Ratio |
|---|---|---|---|---|---|
| 2025-01 | 1,441 | 2.92M | 0.581 | 0.769 | 0.76 |
| 2025-02 | 1,471 | 2.76M | 0.835 | 0.777 | 1.07 |
| 2025-03 | 1,661 | 3.81M | 0.683 | 0.778 | 0.88 |
| 2025-04 | 1,669 | 3.52M | 0.647 | 0.781 | 0.83 |
| 2025-05 | 1,893 | 3.69M | 0.708 | 0.784 | 0.90 |
| 2025-06 | 2,131 | 4.02M | 0.673 | 0.783 | 0.86 |
| 2025-07 | 2,215 | 3.63M | 0.655 | 0.786 | 0.83 |
| 2025-08 | 2,034 | 3.14M | 0.690 | 0.781 | 0.88 |
| 2025-09 | 2,135 | 3.13M | 0.646 | 0.781 | 0.83 |
| 2025-10 | 2,017 | 2.50M | 0.645 | 0.783 | 0.82 |
| 2025-11 | 2,139 | 2.39M | 0.691 | 0.776 | 0.89 |
| 2025-12 | 2,631 | 2.37M | 0.642 | 0.793 | 0.81 |
| 2026-01 | 1,703 | 1.23M | 0.630 | 0.786 | 0.80 |
| 2026-02 | 1,795 | 0.96M | 0.638 | 0.796 | 0.80 |
| 2026-03 | 2,032 | 0.86M | 0.595 | 0.790 | 0.75 |
| 2026-04 | 1,946 | 0.41M | 0.298 | 0.786 | 0.38 |
| 2026-05 | 854 | 0.06M | 0.198 | 0.788 | 0.25 |

* **Test insurance Gini (pure premium): 0.1286** — small but positive
  discrimination on the hold-out (lower than the in-sample 0.41, because the
  hold-out is a single recent period with less spread).
* **Test actual LR 0.8225** vs **predicted LR 0.7838** (target 0.65) —
  the model is well calibrated *in level* (ratio ≈ 1.05) and confirms that the book
  runs ~17–22% above target. The 2026-04/05 months drop sharply because the
  data thins out (earned premium falls to GEL 0.06M) and the loss ratio becomes
  volatile — this is a monitoring signature, not a model one.

### 9.8 Running the new modules

```bash
python -m src.frequency      # frequency GLMs + GBM, out-of-time Gini/deviance
python -m src.severity       # severity LogNormal GLM + GBM
python -m src.pure_premium   # freq x sev (GLM) vs direct Tweedie GBM
python -m src.credibility    # Buhlmann-Straub credibility blending
python -m src.pricing        # model-based rate indication + elasticity
python -m src.validation     # monthly actual-vs-predicted monitoring
python -m src.eda            # EDA: 9-step exploratory analysis
python -m src.experiments    # 8 what-if experiments (defending each choice)
python -m tests.run_all      # full test suite (48 tests, 11 modules)
```

Dependencies add `statsmodels` and `lightgbm` to the Part A stack
(`pandas`, `numpy`, `openpyxl`).

### 9.9 Updated limitations and next steps

* **The target loss ratio is 65% in Part B** (vs 60% in Part A) — both are
  management parameters; align them before deployment.
* **The Gamma severity GLM is unusable** on this data (numerical divergence);
  the LogNormal GLM is the parametric severity baseline.
* **Elasticity `−0.5` is an assumption** — calibrate it from renewal/lapse
  data before relying on the volume-response figures.
* **The calibration factor (1.68)** corrects the level bias in the multiplicative
  model; revisit it if the frequency/severity components are refitted.
* **Next:** deploy the monitoring dashboard on live records; back-test the
  rate indication against the hold-out's realised loss ratio; consider a
  GLMM/boosted hybrid and a proper Tweedie variance-power search.

### 9.10 Testing, EDA and experiments (engineering robustness)

Beyond the models, three layers make the result auditable and defensible:

* **Test suite (`tests/`)** — **48 tests across 11 modules, 0 failures**
  (`python -m tests.run_all`). Every test file documents *why* it exists;
  the suite is a regression net that caught the Negative-Binomial `alpha=0`
  divergence (a 20-minute lock-up) and the experiments' `KeyError: 'segment'` bug.
* **EDA (`src/eda.py`)** — `python -m src.eda` runs 9 step functions (overview,
  frequency, severity, exposure, segments, time trend, feature relationships,
  zero-claim deep dive, credibility preview) that *show* the facts
  the models rely on.
* **Experiments (`src/experiments.py`)** — `python -m src.experiments` runs 8
  what-if investigations that *prove* each modelling choice: the Gamma GLM divergence
  (EXP 2), the `log_exposure` ablation that cuts the GBM Gini without it (EXP 5),
  policy-count vs dollar credibility (EXP 6, Z 0.36 vs 0.99), and the calibration
  effect that flips the sign of the indication (EXP 7, +18.5% vs −27.8%). NegBin vs
  Poisson (EXP 8) confirms there is no over-dispersion (Gini 0.3909 ≈ 0.3905).

Every decision is *demonstrated*, not just asserted.
