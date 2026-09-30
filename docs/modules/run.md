# Documentation — `src/run.py`

> 🇬🇪 ქართული ვერსია: [run.ka.md](run.ka.md)

**Role:** orchestrate the whole Part A pipeline and write the CSV/Excel outputs.
**Depends on:** `load_data`, `segments`, `metrics`, `recommend`. **Used by:** you (CLI entry point).

---

## 1. What it does (in order)
1. `load_analysis_frame()` → policy-level frame.
2. `add_segments()` + `build_segment_key()` → four dimensions + the composite `segment`.
3. `aggregate_overall()` → one-row portfolio summary.
4. `aggregate_by(["segment"])` → 1,056 composite segments; `recommend(portfolio_loss_ratio=…)` → corrections blended with the portfolio indication.
5. `aggregate_by()` on the one- and two-way breakdowns (age, vehicle, deductible, SI, age×vehicle, vehicle×deductible).
6. Write the outputs; print the portfolio + top-15 segments.

---

## 2. Outputs written
| File | Contents |
|---|---|
| `output/segment_recommendations.csv` | 1,056 segments with corrections and action (UTF-8-BOM) |
| `output/portfolio_overall.csv` | one-row portfolio totals |
| `output/casco_segment_analysis.xlsx` | sheets: `Portfolio_Overall`, `Segment_Recommendations`, + 6 breakdown sheets |

Excel is written with `pd.ExcelWriter(engine="openpyxl")`; sheet names are truncated to 31 characters (Excel limit).

---

## 3. Console robustness
```python
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass
```
Georgian segment labels print safely on Windows (cp1252 would otherwise raise `UnicodeEncodeError`).

---

## 4. How to run
```bash
python -m src.run
```
Dependencies: `pandas`, `numpy`, `openpyxl`.

---

## 5. Single-module exploration
Every module also runs on its own (`python -m src.load_data`, `src.segments`, `src.metrics`, `src.recommend`) and prints a quick summary — handy for step-by-step debugging.

## 6. Verification
- [x] exit code 0; all three output files created
- [x] `segment_recommendations.csv` has 1,056 data rows
- [x] the portfolio total matches the `load_data` verification (loss ratio 0.706)
- [x] top segments sorted by earned premium; corrections within ±50%
