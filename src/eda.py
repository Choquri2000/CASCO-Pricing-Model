"""Exploratory data analysis (EDA) for the CASCO portfolio.

Why an EDA module?
Before modelling you have to *understand the data*: its shape, missing cells,
target distributions and — most importantly — the risk signal in each
segment. This module walks through that exploration **step by step, explaining
what each check means**, and (optionally) saves a few diagnostic
plots to the ``output/eda/`` directory.

Run:  ``python -m src.eda``            (prints the full narrative + saves plots)
      ``python -m src.eda --no-plots`` (text only)

Each ``step_*`` function is self-contained and prints what it found and what it
means for modelling. Read the printed output top to bottom, like a report.
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

from . import load_data
from . import segments as sg
from . import features as ft


HERE = os.path.dirname(os.path.abspath(__file__))
PLOT_DIR = os.path.join(HERE, "..", "output", "eda")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _section(title: str):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def _maybe_plot(func, *args, **kwargs):
    """Run a matplotlib plot only if plotting is enabled and available."""
    if not getattr(_maybe_plot, "enabled", True):
        return
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        func(plt, *args, **kwargs)
        os.makedirs(PLOT_DIR, exist_ok=True)
    except Exception as e:  # pragma: no cover - plots are best-effort
        print(f"    (plot skipped: {type(e).__name__}: {e})")


# --------------------------------------------------------------------------- #
# Steps
# --------------------------------------------------------------------------- #
def step_overview(df: pd.DataFrame):
    _section("Step 1 — Overview: shape, types, memory")
    print(f"Rows (policies): {len(df):,}   Columns: {df.shape[1]}")
    print("Why: the policy-level frame is the grain that everything else consumes.")
    print("\nNull-cell ratio by column (worst first):")
    nulls = (df.isna().mean().sort_values(ascending=False))
    print(nulls[nulls > 0].head(12).round(4).to_string())
    print("\nFeature missing-value handling: `carage` and `min_driver_age` are not dropped —")
    print("`carage` is a categorical feature (one-hot encoded), `min_driver_age` is numeric")
    print("(median-imputed in prepare_X). `eligible_driver_count` is fully populated and used.")


def step_target_frequency(df: pd.DataFrame):
    _section("Step 2 — Frequency target (n_claims)")
    nc = df["n_claims"]
    zero_share = (nc == 0).mean()
    print(f"Mean claims/policy : {nc.mean():.3f}")
    print(f"Max claims/policy  : {nc.max()}")
    print(f"Share with 0 claims: {zero_share:.1%}")
    print("Why: most policies have no claim. The model has to learn 'mostly zero' ->"
          " Poisson/NegBin (counts) or Tweedie (zero-inflated) are the right tools,"
          " not plain regression on a continuous target.")
    _maybe_plot(_plot_hist, nc.clip(0, 5), "claim_count_clipped", "Claims per policy (clipped at 5)")


def step_target_severity(df: pd.DataFrame):
    _section("Step 3 — Severity target (incurred per claim)")
    claimed = df.loc[df["n_claims"] > 0, "y_sev"].dropna()
    print(f"Policies with claims : {len(claimed):,}")
    print(f"Severity mean        : {claimed.mean():,.0f}  (strongly skewed tail)")
    print(f"Severity median      : {claimed.median():,.0f}")
    print(f"p95 / p99            : {claimed.quantile(0.95):,.0f} / {claimed.quantile(0.99):,.0f}")
    print(f"Max                  : {claimed.max():,.0f}")
    print("Why: mean >> median and a huge max = right-skewed / heavy-tailed.")
    print("  -> model in log space (LogNormal) or with a tail-robust GBM; a Gamma")
    print("     GLM breaks down on this (which is why we dropped it).")
    _maybe_plot(_plot_hist, np.log1p(claimed.clip(lower=1)), "log_severity",
                "log1p(severity) — should look roughly bell-shaped")


def step_exposure(df: pd.DataFrame):
    _section("Step 4 — Exposure (earned policy-years)")
    exp = df["exposure"]
    print(f"Exposure min/median/max: {exp.min():.3f} / {exp.median():.3f} / {exp.max():.3f} years")
    print(f"Total earned exposure  : {exp.sum():,.0f} policy-years")
    print(f"Share of exposure <= 0 : {(exp <= 0).mean():.2%}")
    print("Why: exposure is the GLM offset / GBM init_score. It is time on risk, not earned"
          " premium — premium already contains the current price the models must judge."
          " Rows with no time on risk (e.g. starting after the extraction date) are dropped.")


def step_segments(df: pd.DataFrame):
    _section("Step 5 — Segment signal (where is the mispricing?)")
    for dim, label in [("client_age_bin", "Age"),
                       ("vehicle_type", "Vehicle"),
                       ("franchise", "Deductible (franchise)"),
                       ("suminsured_usd_bin", "Sum insured (USD)")]:
        g = df.groupby(dim, observed=True)
        t = pd.DataFrame({
            "n_policies": g.size(),
            "loss_ratio": g["incurred_claim"].sum() / g["earned_premium"].sum(),
            "avg_policy_rate": g.apply(lambda d: (d["grosswrittenpremiumgel"] /
                                                  d["suminsuredgel"]).mean(), include_groups=False),
        })
        print(f"\n--- {label} ---")
        print(t.round(4).to_string())
    print("\nWhy: these tables are the story. Young drivers, no-deductible and")
    print("low sum insured run very hot; the rate does not follow the risk -> the book")
    print("is under-priced precisely in these segments (see docs/report.md).")


def step_time_trend(df: pd.DataFrame):
    _section("Step 6 — Time trend (why we split by time, not at random)")
    ef = pd.to_datetime(df["efdate"], errors="coerce")
    df = df.copy()
    df["ym"] = ef.dt.to_period("M").astype(str)
    g = df.groupby("ym").agg(n=("policyid", "size"),
                             incurred=("incurred_claim", "sum"),
                             earned=("earned_premium", "sum"))
    g["lr"] = g["incurred"] / g["earned"]
    print(g.tail(14).round(4).to_string())
    cut = pd.Timestamp("2025-01-01")
    n_train = (ef < cut).sum()
    n_test = (ef >= cut).sum()
    print(f"\nTrain (< 2025-01-01): {n_train:,}   Test (>= 2025-01-01): {n_test:,}")
    print("Why: a random split would leak future policies into training and")
    print("inflate the Gini. Training on the past and testing on the future is the")
    print("honest out-of-time check a pricing model needs before deployment.")


def step_feature_relationships(feat: pd.DataFrame):
    _section("Step 7 — Feature relationships (what predicts risk?)")
    num = ft.NUMERIC_FEATURES
    corr = feat[num + ["y_freq", "y_sev"]].corr()
    print("Correlation of numeric features with frequency / severity:")
    print(corr.loc[num, ["y_freq", "y_sev"]].round(3).to_string())
    print("\nWhy: weak linear correlations are expected — risk is multi-factor and")
    print("non-linear; that is exactly why we also fit tree models (GBM), which")
    print("capture interactions that a linear GLM misses.")


def step_zero_claim_deep_dive(df: pd.DataFrame):
    _section("Step 8 — Zero-claim vs positive-claim deep dive")
    claimed = df[df["n_claims"] > 0]
    print(f"Policies with >=1 claim : {len(claimed):,} ({len(claimed)/len(df):.1%})")
    print(f"Among claimants, payment=0: {(claimed['incurred_claim']==0).sum():,}")
    print("Why: zero-payment claims (a claim exists but nothing was paid)")
    print("are excluded from the severity model (impossible for log/Gamma), but are already")
    print("counted by the frequency model. This separation is intentional.")


def step_credibility_preview(df: pd.DataFrame):
    _section("Step 9 — Credibility preview (within- vs between-segment variance)")
    df = sg.add_segments(df)
    df = sg.build_segment_key(df)
    g = df.groupby("segment", observed=True)
    seg = pd.DataFrame({
        "n": g.size(),
        "pp": g.apply(lambda d: d["incurred_claim"].sum() / d["earned_premium"].clip(lower=1e-6).sum(),
                      include_groups=False),
    })
    overall = df["incurred_claim"].sum() / df["earned_premium"].clip(lower=1e-6).sum()
    print(f"Portfolio pure premium (mu): {overall:.4f}")
    print(f"Segment pure premium: min {seg['pp'].min():.3f} / median {seg['pp'].median():.3f}"
          f" / max {seg['pp'].max():.3f}")
    print(f"Share of segments with <100 policies: {(seg['n']<100).mean():.1%}")
    print("Why: a huge spread of segment pp + many thin segments = the textbook")
    print("case for Bühlmann-Straub credibility (shrink noisy cells toward mu).")


# --------------------------------------------------------------------------- #
# Plot helpers
# --------------------------------------------------------------------------- #
def _plot_hist(plt, series: pd.Series, name: str, title: str):
    plt.figure(figsize=(6, 4))
    plt.hist(series.dropna(), bins=40)
    plt.title(title)
    plt.tight_layout()
    plt.savefig(os.path.join(PLOT_DIR, f"{name}.png"), dpi=90)
    plt.close()


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def main(plot: bool = True):
    _maybe_plot.enabled = plot
    # Segment tables contain Georgian labels (e.g. vehicle types). On Windows the
    # default stdout encoding is cp1252, which cannot represent these characters,
    # so switch to UTF-8 (works both on the console and when redirecting to a file).
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print("CASCO EDA — step-by-step exploration of the analysis frame")
    df = load_data.load_analysis_frame()
    # Build the full frame once: engineered targets/exposure (features.build_features)
    # plus the four rating segments (segments.add_segments). This single frame carries
    # every column the steps need (y_sev, exposure, client_age_bin, franchise, ...),
    # so we avoid KeyErrors such as 'y_sev' on the raw frame.
    full = sg.add_segments(ft.build_features(df))
    step_overview(df)
    step_target_frequency(full)
    step_target_severity(full)
    step_exposure(full)
    step_segments(full)
    step_time_trend(full)
    step_feature_relationships(full)
    step_zero_claim_deep_dive(full)
    step_credibility_preview(full)
    if plot:
        print(f"\nPlots (if any) saved to: {os.path.abspath(PLOT_DIR)}")
    print("\nEDA complete.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-plots", action="store_true", help="skip matplotlib plots")
    args = ap.parse_args()
    main(plot=not args.no_plots)
