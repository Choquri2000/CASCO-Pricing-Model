"""Additional experiments - going beyond the baseline models.

Why an experiments module?
The production modules each pick one sensible configuration. But a strong
candidate should be able to answer "what happens if we change X?" This module runs
such *what-if*s and prints the result with an explanation of what it teaches:

  1. Frequency GBM hyper-parameter sweep (tree size / learning rate).
  2. Severity: show the Gamma GLM divergence (why we dropped it).
  3. Severity: LogNormal vs GBM, with/without claim-count weights.
  4. Pure premium: Tweedie power sweep (1.1 .. 1.7) against the two-part model.
  5. Exposure handling in the GBM: init_score offset vs log_exposure feature vs none.
  6. Credibility sensitivity: policy count vs dollar exposure for n_i (the Z~1 bug).
  7. Level bias: LogNormal smearing vs the portfolio calibration factor.
  8. NegBin vs Poisson: is there over-dispersion?
  9. Metric check: unweighted Gini on raw amounts vs the exposure-weighted Gini.

All Gini values are exposure-weighted on the predicted rate (`frequency.gini_normalized`)
unless stated otherwise.

Run:  ``python -m src.experiments``
"""

from __future__ import annotations

import sys
import warnings
from functools import lru_cache

import numpy as np
import pandas as pd
import statsmodels.api as sm

from . import load_data
from . import features as ft
from . import segments as sg
from . import frequency as fr
from . import severity as sv
from . import pure_premium as pp
from . import credibility as cr
from . import pricing as pr


@lru_cache(maxsize=1)
def _segmented_features():
    # Loaded once: the raw load is the slow part of every experiment.
    raw = load_data.load_analysis_frame()
    raw = sg.add_segments(raw)
    raw = sg.build_segment_key(raw)
    return ft.build_features(raw)


def _split():
    return ft.make_time_split(_segmented_features())


def _fit_gbm(X, y, offset_exposure=None, weight=None, num_leaves=31,
             learning_rate=0.05, objective="poisson"):
    import lightgbm as lgb
    m = lgb.LGBMRegressor(objective=objective, n_estimators=300,
                          learning_rate=learning_rate, num_leaves=num_leaves,
                          min_child_samples=50, verbose=-1)
    kw = {}
    if offset_exposure is not None:
        kw["init_score"] = np.log(np.asarray(offset_exposure, dtype=float))
    if weight is not None:
        kw["sample_weight"] = np.asarray(weight, dtype=float)
    m.fit(np.asarray(X, dtype=float), np.asarray(y, dtype=float), **kw)
    return m


def exp_frequency_gbm_sweep():
    print("\n=== EXP 1: frequency GBM hyper-parameter sweep ===")
    print("Why: tree depth and learning rate trade off bias/variance. We check")
    print("that Gini/deviance are stable on a small grid (not over-fit-sensitive).")
    train, test = _split()
    tr = train[train["exposure"] > 0]; te = test[test["exposure"] > 0]
    Xtr, Xte = fr.prepare_X(tr, te)
    ytr, yte = tr["y_freq"].values, te["y_freq"].values
    etr, ete = tr["exposure"].values, te["exposure"].values
    rows = []
    for nl in [15, 31, 63]:
        for lr in [0.05, 0.10]:
            m = _fit_gbm(Xtr, ytr, offset_exposure=etr, num_leaves=nl, learning_rate=lr)
            pred = fr.predict_gbm(m, Xte, ete)
            rows.append({"num_leaves": nl, "lr": lr,
                         "gini": round(fr.gini_normalized(yte, pred, ete), 4),
                         "poisson_dev": round(fr.poisson_deviance(yte, pred), 1)})
    print(pd.DataFrame(rows).to_string(index=False))


def exp_severity_gamma_divergence():
    print("\n=== EXP 2: severity - Gamma GLM divergence (why we dropped it) ===")
    train, test = _split()
    tr = train[(train["n_claims"] > 0) & (train["y_sev"] > 0)].copy()
    te = test[(test["n_claims"] > 0) & (test["y_sev"] > 0)].copy()
    Xtr, Xte = sv.prepare_X(tr, te)
    ytr, yte = tr["y_sev"].values, te["y_sev"].values
    wte = te["n_claims"].values
    Xc_te = sm.add_constant(np.asarray(Xte, dtype=float), has_constant="add")

    # LogNormal (our chosen parametric model)
    ln = sv.fit_lognormal(Xtr, ytr)
    ln_pred = sv.predict_lognormal(ln, Xc_te)
    print(f"LogNormal GLM : Gini={sv.severity_gini(yte, ln_pred, wte):.4f}  "
          f"max_pred={ln_pred.max():,.0f}  (sane)")

    # Gamma GLM - try the fit and inspect the divergence
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            gam = sm.GLM(ytr, sm.add_constant(np.asarray(Xtr, dtype=float)),
                         family=sm.families.Gamma()).fit(disp=0)
            gam_pred = gam.predict(Xc_te)
            finite = np.isfinite(gam_pred).all()
            print(f"Gamma GLM    : finite={finite}  max_pred={np.nanmax(gam_pred):.3g}  "
                  f"Gini={sv.severity_gini(yte, gam_pred, wte):.4f}")
            print("Lesson: on this heavy-tailed severity, Gamma IRLS with its default")
            print("inverse link can overshoot or fall into an inversely-ranked optimum.")
            print("LogNormal is the stable choice.")
        except Exception as e:
            print(f"Gamma GLM    : fit failed ({type(e).__name__}) -> confirms the divergence.")


def exp_severity_weights():
    print("\n=== EXP 3: severity - LogNormal vs GBM, with/without claim weights ===")
    train, test = _split()
    tr = train[(train["n_claims"] > 0) & (train["y_sev"] > 0)].copy()
    te = test[(test["n_claims"] > 0) & (test["y_sev"] > 0)].copy()
    Xtr, Xte = sv.prepare_X(tr, te)
    ytr, yte = tr["y_sev"].values, te["y_sev"].values
    wtr, wte = tr["n_claims"].clip(lower=1).values, te["n_claims"].values
    ln = sv.fit_lognormal(Xtr, ytr)
    ln_pred = sv.predict_lognormal(ln, sm.add_constant(np.asarray(Xte, dtype=float), has_constant="add"))
    gbm_w = _fit_gbm(Xtr, ytr, weight=wtr, objective="gamma")
    gbm_nw = _fit_gbm(Xtr, ytr, objective="gamma")
    print(f"LogNormal GLM         : Gini={sv.severity_gini(yte, ln_pred, wte):.4f}")
    print(f"GBM (claim-weighted)  : Gini={sv.severity_gini(yte, gbm_w.predict(np.asarray(Xte, dtype=float)), wte):.4f}")
    print(f"GBM (unweighted)      : Gini={sv.severity_gini(yte, gbm_nw.predict(np.asarray(Xte, dtype=float)), wte):.4f}")
    print("Lesson: weighting by claim count gives high-information policies more")
    print("influence; the effect is small here, but principled.")


def exp_pure_premium_tweedie_power():
    print("\n=== EXP 4: pure premium - Tweedie power sweep vs the two-part model ===")
    train, test = _split()
    tr_pp = train[train["exposure"] > 0].copy()
    te_pp = test[test["exposure"] > 0].copy()
    Xtr, Xte = fr.prepare_X(tr_pp, te_pp)
    ytr, yte = tr_pp["y_pp"].values, te_pp["y_pp"].values
    ete = te_pp["exposure"].values
    rows = []
    for p in [1.1, 1.3, 1.5, 1.7]:
        m = pp.fit_tweedie(Xtr, ytr, tr_pp["exposure"].values, power=p)
        pred = fr.predict_gbm(m, Xte, ete)
        rows.append({"tweedie_power": p, "gini": round(fr.gini_normalized(yte, pred, ete), 4),
                     "deviance": round(pp.tweedie_deviance(yte, pred, p), 1)})
    # two-part baseline
    base = pp.train_and_evaluate(train, test)
    print(pd.DataFrame(rows).to_string(index=False))
    print(base[["model", "gini", "tweedie_deviance"]].round(4).to_string(index=False))
    print("Lesson: compare every power with the two-part model AND with the current")
    print("premium — a model only adds value where it out-ranks the existing tariff.")


def exp_gbm_exposure_handling():
    print("\n=== EXP 5: exposure handling in the frequency GBM ===")
    train, test = _split()
    tr = train[train["exposure"] > 0]; te = test[test["exposure"] > 0]
    ytr, yte = tr["y_freq"].values, te["y_freq"].values
    etr, ete = tr["exposure"].values, te["exposure"].values
    Xtr, Xte = fr.prepare_X(tr, te)
    Xtr_f, Xte_f = fr.prepare_X(tr, te, add_log_exposure=True)

    m_offset = _fit_gbm(Xtr, ytr, offset_exposure=etr)
    m_feature = _fit_gbm(Xtr_f, ytr)
    m_none = _fit_gbm(Xtr, ytr)
    preds = {
        "init_score offset (production)": fr.predict_gbm(m_offset, Xte, ete),
        "log_exposure as a feature": m_feature.predict(np.asarray(Xte_f, dtype=float)),
        "no exposure information": m_none.predict(np.asarray(Xte, dtype=float)),
    }
    for name, pred in preds.items():
        print(f"{name:32s}: Gini={fr.gini_normalized(yte, pred, ete):.4f}  "
              f"Poisson dev={fr.poisson_deviance(yte, pred):,.1f}  "
              f"pred/actual={pred.sum() / yte.sum():.3f}")
    print("Lesson: trees have no native offset. init_score gives them exactly the GLM")
    print("offset; without any exposure information the expected counts are mis-scaled")
    print("for part-year policies.")


def exp_credibility_dollar_exposure():
    print("\n=== EXP 6: credibility - policy count vs dollar exposure for n_i ===")
    train, _ = _split()
    seg, mu, k = cr.buhlmann_straub(train)
    print(f"By policy count   : mean Z = {seg['Z'].mean():.4f}  (real shrinkage)")
    # recompute Z with n_i = dollar exposure (the old bug)
    n_dollar = seg["exposure"]
    k_d = (np.average(seg["var_pp"], weights=n_dollar) /
           np.average((seg["mean_pp"] - mu) ** 2, weights=n_dollar))
    Z_dollar = (n_dollar / (n_dollar + k_d))
    print(f"By dollar exposure: mean Z = {Z_dollar.mean():.4f}  (~1 -> no shrinkage)")
    print("Lesson: dollar exposure dwarfs k, so Z~1 for every")
    print("segment and credibility blending does nothing. n_i must be a count of risks.")


def exp_level_bias():
    print("\n=== EXP 7: level bias - LogNormal smearing vs portfolio calibration ===")
    train, test = _split()
    for smearing in (False, True):
        calib = pp.calibration_factor(train, smearing=smearing)
        pred = pp.predict(train, test, smearing=smearing)
        rec_raw = pr.recommend_v2(test, pred, target_loss_ratio=0.65)
        rec_cal = pr.recommend_v2(test, pred * calib, target_loss_ratio=0.65)
        label = "with smearing   " if smearing else "without smearing"
        print(f"{label}: calibration factor = {calib:.3f}   mean rate change "
              f"uncalibrated = {rec_raw['rate_change'].mean():+.4f}, "
              f"calibrated = {rec_cal['rate_change'].mean():+.4f}")
    print("Lesson: exp(E[log S]) is the median of a lognormal, not the mean. Without the")
    print("smearing factor the model under-predicts every claim, and a large portfolio")
    print("'calibration factor' is needed to hide it; with smearing the factor is ~1.")


def exp_negbin_vs_poisson():
    print("\n=== EXP 8: NegBin vs Poisson - is there over-dispersion? ===")
    train, test = _split()
    tr = train[train["exposure"] > 0]; te = test[test["exposure"] > 0]
    Xtr, Xte = fr.prepare_X(tr, te)
    ytr, yte = tr["y_freq"].values, te["y_freq"].values
    etr, ete = tr["exposure"].values, te["exposure"].values
    pois = fr.fit_poisson(Xtr, ytr, etr)
    nb = fr.fit_negbin(Xtr, ytr, etr)
    off = np.log(ete)
    Xc = sm.add_constant(np.asarray(Xte, dtype=float), has_constant="add")
    p_pred = pois.predict(Xc, offset=off)
    n_pred = nb.predict(Xc, offset=off)
    alpha = nb.params[-1] if hasattr(nb, "params") and len(nb.params) > Xc.shape[1] else 0.0
    print(f"Poisson Gini={fr.gini_normalized(yte, p_pred, ete):.4f}   "
          f"NegBin Gini={fr.gini_normalized(yte, n_pred, ete):.4f}   NegBin alpha={alpha:.4f}")
    print("Lesson: when the rankings coincide, over-dispersion does not change the")
    print("risk ordering; NegBin matters for confidence intervals, not for the tariff.")


def exp_gini_metric_check():
    print("\n=== EXP 9: which Gini? raw amounts vs exposure-weighted rate ===")
    train, test = _split()
    te = test[test["exposure"] > 0]
    y, e, prem = te["y_pp"].values, te["exposure"].values, te["earned_premium"].values
    pred = pp.predict(train, test)
    print(f"{'predictor':28s} {'unweighted Gini':>16s} {'exposure-weighted':>18s}")
    for name, p in [("earned premium only", prem), ("exposure (years) only", e),
                    ("Freq x Sev model", pred)]:
        print(f"{name:28s} {fr.gini(y, p):16.4f} {fr.gini_normalized(y, p, e):18.4f}")
    print("Lesson: on raw amounts even 'years on risk' or the premium itself look like")
    print("good models, because bigger policies simply have bigger losses. The weighted")
    print("Gini on the predicted rate removes that effect.")


def main():
    # Switch stdout to UTF-8 so any (Georgian) label prints safely on Windows.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print("CASCO - additional experiments (what-if investigations)")
    exp_frequency_gbm_sweep()
    exp_severity_gamma_divergence()
    exp_severity_weights()
    exp_pure_premium_tweedie_power()
    exp_gbm_exposure_handling()
    exp_credibility_dollar_exposure()
    exp_level_bias()
    exp_negbin_vs_poisson()
    exp_gini_metric_check()
    print("\nExperiments complete.")


if __name__ == "__main__":
    main()
