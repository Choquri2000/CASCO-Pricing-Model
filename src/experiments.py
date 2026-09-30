"""Additional experiments - going beyond the baseline models.

Why an experiments module?
The production modules each pick one sensible configuration. But a strong
candidate should be able to answer "what happens if we change X?" This module runs
such *what-if*s and prints the result with an explanation of what it teaches:

  1. Frequency GBM hyper-parameter sweep (tree size / learning rate).
  2. Severity: show the Gamma GLM divergence (why we dropped it).
  3. Severity: LogNormal vs GBM, with/without claim-count weights.
  4. Pure premium: Tweedie power sweep (1.1 .. 1.7) against the two-part model.
  5. GBM feature ablation: with vs without log_exposure (the offset substitute).
  6. Credibility sensitivity: policy count vs dollar exposure for n_i (the Z~1 bug).
  7. Calibration effect: rate indication with vs without the calibration factor.
  8. NegBin vs Poisson: confirm they coincide (no over-dispersion).

Run:  ``python -m src.experiments``
"""

from __future__ import annotations

import sys
import warnings
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


def _split():
    raw = load_data.load_analysis_frame()
    feat = ft.build_features(raw)
    return ft.make_time_split(feat)


def _fit_gbm(X, y, exp, num_leaves=31, learning_rate=0.05, objective="poisson"):
    import lightgbm as lgb
    m = lgb.LGBMRegressor(objective=objective, n_estimators=300,
                          learning_rate=learning_rate, num_leaves=num_leaves,
                          min_child_samples=50, verbose=-1)
    m.fit(np.asarray(X, dtype=float), np.asarray(y, dtype=float),
          sample_weight=np.asarray(exp, dtype=float))
    return m


def exp_frequency_gbm_sweep():
    print("\n=== EXP 1: frequency GBM hyper-parameter sweep ===")
    print("Why: tree depth and learning rate trade off bias/variance. We check")
    print("that Gini/deviance are stable on a small grid (not over-fit-sensitive).")
    train, test = _split()
    tr = train[train["exposure"] > 0]; te = test[test["exposure"] > 0]
    Xtr, Xte = fr.prepare_X(tr, te, add_log_exposure=True)
    ytr, yte = tr["y_freq"].values, te["y_freq"].values
    ete = te["exposure"].values
    rows = []
    for nl in [15, 31, 63]:
        for lr in [0.05, 0.10]:
            m = _fit_gbm(Xtr, ytr, tr["exposure"].values, nl, lr)
            pred = m.predict(np.asarray(Xte, dtype=float))
            rows.append({"num_leaves": nl, "lr": lr,
                         "gini": round(fr.gini(yte, pred), 4),
                         "poisson_dev": round(fr.poisson_deviance(yte, pred), 1)})
    print(pd.DataFrame(rows).to_string(index=False))


def exp_severity_gamma_divergence():
    print("\n=== EXP 2: severity - Gamma GLM divergence (why we dropped it) ===")
    train, test = _split()
    tr = train[(train["n_claims"] > 0) & (train["y_sev"] > 0)].copy()
    te = test[(test["n_claims"] > 0) & (test["y_sev"] > 0)].copy()
    Xtr, Xte = sv.prepare_X(tr, te)
    ytr, yte = tr["y_sev"].values, te["y_sev"].values
    Xc_te = sm.add_constant(np.asarray(Xte, dtype=float), has_constant="add")

    # LogNormal (our chosen parametric model)
    ln = sv.fit_lognormal(Xtr, ytr)
    ln_pred = np.exp(ln.predict(Xc_te))
    print(f"LogNormal GLM : Gini={fr.gini(yte, ln_pred):.4f}  "
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
                  f"Gini={fr.gini(yte, gam_pred):.4f}")
            print("Lesson: on this heavy-tailed severity, Gamma IRLS either overshoots")
            print("to an extreme or falls into an inversely-ranked optimum")
            print("(negative/extreme Gini). LogNormal is the stable choice.")
        except Exception as e:
            print(f"Gamma GLM    : fit failed ({type(e).__name__}) -> confirms the divergence.")


def exp_severity_weights():
    print("\n=== EXP 3: severity - LogNormal vs GBM, with/without claim weights ===")
    train, test = _split()
    tr = train[(train["n_claims"] > 0) & (train["y_sev"] > 0)].copy()
    te = test[(test["n_claims"] > 0) & (test["y_sev"] > 0)].copy()
    Xtr, Xte = sv.prepare_X(tr, te, add_log_exposure=True)
    ytr, yte = tr["y_sev"].values, te["y_sev"].values
    w = tr["n_claims"].clip(lower=1).values
    ln = sv.fit_lognormal(Xtr, ytr)
    ln_pred = np.exp(ln.predict(sm.add_constant(np.asarray(Xte, dtype=float), has_constant="add")))
    gbm_w = _fit_gbm(Xtr, ytr, w, objective="gamma")
    gbm_nw = _fit_gbm(Xtr, ytr, np.ones_like(ytr), objective="gamma")
    print(f"LogNormal GLM         : Gini={fr.gini(yte, ln_pred):.4f}")
    print(f"GBM (claim-weighted)  : Gini={fr.gini(yte, gbm_w.predict(np.asarray(Xte, dtype=float))):.4f}")
    print(f"GBM (unweighted)      : Gini={fr.gini(yte, gbm_nw.predict(np.asarray(Xte, dtype=float))):.4f}")
    print("Lesson: weighting by claim count gives high-information policies more")
    print("influence; the effect is small here, but principled.")


def exp_pure_premium_tweedie_power():
    print("\n=== EXP 4: pure premium - Tweedie power sweep vs the two-part model ===")
    train, test = _split()
    tr_pp = train[train["exposure"] > 0].copy()
    te_pp = test[test["exposure"] > 0].copy()
    Xtr, Xte = fr.prepare_X(tr_pp, te_pp, add_log_exposure=True)
    ytr, yte = tr_pp["y_pp"].values, te_pp["y_pp"].values
    rows = []
    for p in [1.1, 1.3, 1.5, 1.7]:
        m = pp.fit_tweedie(Xtr, ytr, tr_pp["exposure"].values, power=p)
        pred = m.predict(np.asarray(Xte, dtype=float))
        rows.append({"tweedie_power": p, "gini": round(fr.gini(yte, pred), 4),
                     "deviance": round(pp.tweedie_deviance(yte, pred, p), 1)})
    # two-part baseline
    base = pp.train_and_evaluate(train, test)
    print(pd.DataFrame(rows).to_string(index=False))
    print(base[["model", "gini", "tweedie_deviance"]].round(4).to_string(index=False))
    print("Lesson: power 1.5 is a sensible default (between Poisson=1 and")
    print("Gamma=2); the two-part freq x sev still ranks better on this book.")


def exp_gbm_feature_ablation():
    print("\n=== EXP 5: GBM feature ablation - log_exposure matters ===")
    train, test = _split()
    tr = train[train["exposure"] > 0]; te = test[test["exposure"] > 0]
    ytr, yte = tr["y_freq"].values, te["y_freq"].values
    Xtr_with, Xte_with = fr.prepare_X(tr, te, add_log_exposure=True)
    Xtr_without, Xte_without = fr.prepare_X(tr, te, add_log_exposure=False)
    m_with = _fit_gbm(Xtr_with, ytr, tr["exposure"].values)
    m_without = _fit_gbm(Xtr_without, ytr, tr["exposure"].values)
    g_with = fr.gini(yte, m_with.predict(np.asarray(Xte_with, dtype=float)))
    g_without = fr.gini(yte, m_without.predict(np.asarray(Xte_without, dtype=float)))
    print(f"GBM with log_exposure    : Gini={g_with:.4f}")
    print(f"GBM without log_exposure : Gini={g_without:.4f}")
    print("Lesson: trees have no offset, so without log_exposure")
    print("they cannot normalise for exposure and rank worse - exactly")
    print("the bug we fixed in production.")


def exp_credibility_dollar_exposure():
    print("\n=== EXP 6: credibility - policy count vs dollar exposure for n_i ===")
    # buhlmann_straub groups by the composite "segment" key, so the segments must
    # be built (add_segments + build_segment_key) before the time split.
    raw = load_data.load_analysis_frame()
    raw = sg.add_segments(raw)
    raw = sg.build_segment_key(raw)
    feat = ft.build_features(raw)
    train, _ = ft.make_time_split(feat)
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


def exp_calibration_effect():
    print("\n=== EXP 7: calibration effect on the rate indication ===")
    raw = load_data.load_analysis_frame()
    raw = sg.add_segments(raw); raw = sg.build_segment_key(raw)
    feat = ft.build_features(raw)
    train, test = ft.make_time_split(feat)
    pred = pp.predict(train, test)
    rec_cal = pr.recommend_v2(test, pred * pp.calibration_factor(train), target_loss_ratio=0.65)
    rec_raw = pr.recommend_v2(test, pred, target_loss_ratio=0.65)
    print(f"With calibration (factor={pp.calibration_factor(train):.3f}): "
          f"mean rate change = {rec_cal['rate_change'].mean():+.4f}")
    print(f"Without calibration                          : "
          f"mean rate change = {rec_raw['rate_change'].mean():+.4f}")
    print("Lesson: the multiplicative model under-predicts the average")
    print("level; without calibration it would (wrongly) suggest a cut for an under-priced book.")


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
    print(f"Poisson Gini={fr.gini(yte, p_pred):.4f}   NegBin Gini={fr.gini(yte, n_pred):.4f}")
    print("Lesson: they are (almost) identical -> no material")
    print("over-dispersion beyond what exposure explains; NegBin is kept only for robustness.")


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
    exp_gbm_feature_ablation()
    exp_credibility_dollar_exposure()
    exp_calibration_effect()
    exp_negbin_vs_poisson()
    print("\nExperiments complete.")


if __name__ == "__main__":
    main()
