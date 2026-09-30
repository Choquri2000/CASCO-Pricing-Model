# Documentation — `src/recommend.py`

> 🇬🇪 ქართული ვერსია: [recommend.ka.md](recommend.ka.md)

**Role:** turn segment loss ratios into credibility-weighted, capped price corrections.
**Depends on:** the output of `metrics.aggregate_by`. **Used by:** `run`.

---

## 1. Core idea
Compare each segment's observed loss ratio with a **target** loss ratio. A segment running hotter than target is under-priced → load it; cooler → discount it. Segments with few claims are noisy, so their own indication is blended with the **portfolio-wide** indication.

---

## 2. Formulas

### 2.1 Raw correction (the segment's own experience)
```
raw_correction = (loss_ratio / target_loss_ratio) - 1
```
- If `loss_ratio > target` → positive (price increase); `< target` → negative.
- `NaN` loss ratio (no earned premium yet) → `raw_correction = NaN` → action "No data".

### 2.2 Base correction (complement of credibility)
```
base_correction = (portfolio_loss_ratio / target_loss_ratio) - 1
```
On this book: 70.6% / 60% − 1 = **+17.7%**. A segment with no credible experience moves with the whole book instead of staying at "no change".

### 2.3 Credibility (limited fluctuation, square-root rule)
```
credibility = min(1, sqrt(n_claims / full_credibility_claims))
```
`full_credibility_claims = 1,082` is the classical standard for estimating the claim frequency within ±5% with 90% probability.

### 2.4 Recommended correction (capped)
```
recommended_correction = clip(credibility * raw_correction + (1 - credibility) * base_correction,
                              -max_correction, +max_correction)
relative_to_portfolio  = (1 + recommended_correction) / (1 + base_correction) - 1
```
`relative_to_portfolio` shows where to load **more** (> 0) or **less** (< 0) than the book as a whole.

### 2.5 Recommended rate and % change
```
recommended_premium_rate = premium_rate * (1 + recommended_correction)
recommended_rate_change_pct = recommended_correction * 100
```

### 2.6 Action label
```
action = "Increase"  if recommended_correction >= 0.05
       = "Decrease"  if recommended_correction <= -0.05
       = "Hold"      otherwise      ("No data" if there is no loss ratio)
```

---

## 3. Default parameters
| Parameter | Default | Meaning |
|---|---|---|
| `target_loss_ratio` | `0.60` | acceptable loss ratio (management assumption) |
| `full_credibility_claims` | `1,082` | claims needed for full credibility |
| `max_correction` | `0.50` | cap at ±50% |
| `portfolio_loss_ratio` | computed from the input | complement of credibility; `run.py` passes the portfolio figure so every breakdown uses the same base |

All are function arguments — change them without touching the logic.

---

## 4. Function: `recommend(seg_metrics, ...) -> DataFrame`
Adds the columns: `credibility, raw_correction, base_correction, recommended_correction,
relative_to_portfolio, recommended_premium_rate, recommended_rate_change_pct, action`.

### `summarize_recommendations(rec) -> DataFrame`
Returns a compact view (segment dimensions + key metrics + corrections + action), sorted by `earned_premium` descending. Columns are selected only if they exist.

---

## 5. Results on the real data (1,056 composite segments)
- Median credibility 0.068; 16 segments are fully credible.
- Actions: Increase 1,044 · Hold 8 · Decrease 4 — the whole book needs +17.7%.
- Relative to the book: **238** segments need more than +5% on top of it, **90** need more than 5% less.

v1 used `credibility = min(1, earned_premium / GEL 5M)` with a zero complement: the median credibility was 0.003 and 1,205 of 1,262 segments were on "Hold". See the [methodology review](../review.md).

## 6. Verification (see `tests/test_recommend.py`)
- [x] a segment with 0 claims gets exactly the base correction; a fully credible one keeps its own
- [x] credibility follows the square-root rule and stays in [0, 1]
- [x] thin segments sit closer to the base correction than their raw correction does
- [x] corrections never exceed ±0.50; `action` matches the ±5% threshold
