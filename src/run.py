"""End-to-end pipeline runner for the CASCO claims-cost / underwriting
model.

Run from the project root:

    python -m src.run

It:
  1. loads and cleans the raw data (load_data)
  2. derives the four risk segments (segments)
  3. computes loss-ratio / premium-rate metrics (metrics)
  4. generates price-adjustment recommendations (recommend)
  5. writes CSV + Excel outputs to the output/ directory
"""

from __future__ import annotations

import os
import sys

import pandas as pd

# Make sure Georgian (and other non-ASCII) segment labels print safely
# on any console (otherwise Windows cp1252 would raise
# UnicodeEncodeError).
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:  # pragma: no cover - not every interpreter has reconfigure
    pass

from .load_data import load_analysis_frame
from .segments import add_segments, build_segment_key
from .metrics import aggregate_by, aggregate_overall
from .recommend import recommend, summarize_recommendations

HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(HERE, "..", "output")

# One- and two-way breakdowns reported alongside the full composite
# segment.
DIMENSION_BREAKDOWNS = [
    ["client_age_bin"],
    ["vehicle_type"],
    ["franchise"],
    ["suminsured_usd_bin"],
    ["client_age_bin", "vehicle_type"],
    ["vehicle_type", "franchise"],
]


def run() -> dict[str, pd.DataFrame]:
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("Loading and cleaning data ...")
    frame = load_analysis_frame()
    print(f"  analysis frame: {frame.shape[0]:,} policies")

    print("Deriving risk segments ...")
    frame = add_segments(frame)
    frame = build_segment_key(frame)

    print("Computing portfolio metrics ...")
    overall = aggregate_overall(frame).to_frame(name="value")

    print("Aggregating by composite segment ...")
    seg = aggregate_by(frame, ["segment"])
    rec = recommend(seg)
    rec_summary = summarize_recommendations(rec)

    # Dimension breakdowns.
    breakdowns: dict[str, pd.DataFrame] = {}
    for dims in DIMENSION_BREAKDOWNS:
        key = "_x_".join(dims)
        bd = aggregate_by(frame, dims)
        bd = recommend(bd)
        breakdowns[key] = bd

    # ---- Write outputs -------------------------------------------------
    csv_path = os.path.join(OUTPUT_DIR, "segment_recommendations.csv")
    rec_summary.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"  wrote {csv_path}")

    overall_csv = os.path.join(OUTPUT_DIR, "portfolio_overall.csv")
    overall.to_csv(overall_csv, encoding="utf-8-sig")
    print(f"  wrote {overall_csv}")

    xlsx_path = os.path.join(OUTPUT_DIR, "casco_segment_analysis.xlsx")
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as xw:
        overall.reset_index().rename(columns={"index": "metric"}).to_excel(
            xw, sheet_name="Portfolio_Overall", index=False
        )
        rec_summary.to_excel(xw, sheet_name="Segment_Recommendations", index=False)
        for key, bd in breakdowns.items():
            sheet = key[:31]  # Excel sheet-name length limit
            bd.to_excel(xw, sheet_name=sheet, index=False)
    print(f"  wrote {xlsx_path}")

    # ---- Console summary ---------------------------------------------------
    print("\n=== Portfolio total ===")
    print(overall.to_string())

    print("\n=== Top 15 segments by earned premium ===")
    with pd.option_context("display.max_rows", 15, "display.width", 220):
        print(rec_summary.head(15).to_string(index=False))

    return {
        "frame": frame,
        "overall": overall,
        "segment_recommendations": rec_summary,
        "breakdowns": breakdowns,
    }


if __name__ == "__main__":
    run()
