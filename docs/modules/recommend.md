# Documentation — `src/recommend.py`

> 🇬🇪 ქართული ვერსია: [recommend.ka.md](recommend.ka.md)

**Role:** turn segment loss ratios into credibility-weighted, capped price corrections.
**Depends on:** the output of `metrics.aggregate_by`. **Used by:** `run`.

---

## 1. Core idea
Compare each segment's observed loss ratio with a **target** loss ratio. A segment running hotter than target is under-priced → load it; cooler → discount it.

---

## 2. Formulas

### 2.1 Raw correction
```
raw_correction = (loss_ratio / target_loss_ratio) - 1
```
- If `loss_ratio == target` → 0.
- If `loss_ratio > target` → positive (price increase).
- If `loss_ratio < target` → negative (price decrease).
- `NaN` loss ratio (no data) → `raw_correction = NaN` (no signal).

### 2.2 Credibility (linear shrinkage)
```
credibility = min(1, earned_premium / full_credibility_premium)
```
Thin segments (low earned premium) get low credibility → their correction is shrunk toward 0.

### 2.3 Recommended correction (capped)
```
recommended_correction = clip(raw_correction * credibility, -max_correction, +max_correction)
```

### 2.4 Recommended rate and % change
```
recommended_premium_rate = premium_rate * (1 + recommended_correction)
recommended_rate_change_pct = recommended_correction * 100
```

### 2.5 Action label
```
action = "Increase"  if recommended_correction >= 0.05
       = "Decrease"  if recommended_correction <= -0.05
       = "Hold"      otherwise
```

---

## 3. Default parameters
| Parameter | Default | Meaning |
|---|---|---|
| `target_loss_ratio` | `0.60` | acceptable loss ratio (management assumption) |
| `full_credibility_premium` | `5_000_000` GEL | earned premium for full credibility |
| `max_correction` | `0.50` | cap at ±50% |

All are function arguments — change them without touching the logic.

---

## 4. Function: `recommend(seg_metrics, ...) -> DataFrame`
Adds the columns: `credibility, raw_correction, recommended_correction,
recommended_premium_rate, recommended_rate_change_pct, action`.
- `raw` is computed only where `loss_ratio` is valid (`lr.notna() & lr >= 0`).
- `shrunk = raw * credibility`, then clipped.

### `summarize_recommendations(rec) -> DataFrame`
Returns a compact view (segment dimensions + key metrics + corrections + action), sorted by `earned_premium` descending. Columns are selected only if they exist.

---

## 5. Syntax notes
- `np.minimum(1.0, earned / full)` — vectorised credibility.
- `shrunk.clip(-max_correction, max_correction)` enforces the cap.
- `raw.where(lr.notna() & (lr >= 0))` keeps NaN where there is no loss-ratio signal.

## 6. Verification
- [x] segment with `loss_ratio=0.526` (target 0.60) → correction ≈ −0.12 (−12%)
- [x] fully credible segment (earned ≥ 5M) → `credibility = 1.0`
- [x] corrections never exceed ±0.50
- [x] `action` matches the ±5% threshold
