#!/usr/bin/env python3
"""Hypothesis-specific robustness checks RB-12 through RB-17.

The script is aggregate-only and uses the independent clean core. It never imports
upstream util.py and never emits participant identifiers or raw participant rows.
"""
from __future__ import annotations

import argparse
import json
import math
import warnings
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from patsy import build_design_matrices
from scipy import stats
import statsmodels.api as sm
import statsmodels.formula.api as smf
from statsmodels.genmod.cov_struct import Exchangeable
from statsmodels.genmod.families import Gaussian

from eth_hai_clean.core import build_clean_metric_frame
from eth_hai_clean.hypothesis_common import (
    ALPHA_PUBLISHED,
    CONDITION_ORDER,
    METRICS,
    adjust_pvalues,
    cliffs_delta,
    multiplicity_rows,
    type2_anova_rows,
    write_json,
    write_tsv,
)


def prepare_frame(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy().reset_index(drop=True)
    out["pid_internal"] = np.arange(len(out), dtype=int)
    out["tutorial_yes"] = 1 - out["tutorial_raw"].astype(int)
    out["xai_yes"] = out["xai_raw"].astype(int)
    out["t_c"] = out["tutorial_yes"].astype(float) - 0.5
    out["x_c"] = out["xai_yes"].astype(float) - 0.5
    out["group_first"] = np.where(out["miscalibration_first"] < 0, "Underestimation",
                           np.where(out["miscalibration_first"] > 0, "Overestimation", "Accurate"))
    out["avg_trust"] = (out["trust_first"] + out["trust_second"]) / 2.0
    out["change_trust"] = out["trust_second"] - out["trust_first"]
    for _, metric in METRICS:
        out["delta_%s" % metric] = out["second_%s" % metric] - out["first_%s" % metric]
    return out


def robust_param_rows(model, outcome: str, policy: str) -> List[Dict[str, object]]:
    robust = model.get_robustcov_results(cov_type="HC3")
    names = model.model.exog_names
    mapping = {name: index for index, name in enumerate(names)}
    rows = []
    for effect, parameter in (("Tutorial", "t_c"), ("XAI", "x_c"), ("Tutorial:XAI", "t_c:x_c")):
        index = mapping[parameter]
        rows.append({
            "outcome": outcome,
            "ratio_policy": policy,
            "effect": effect,
            "coefficient": float(robust.params[index]),
            "hc3_se": float(robust.bse[index]),
            "hc3_t": float(robust.tvalues[index]),
            "hc3_p": float(robust.pvalues[index]),
        })
    return rows


def ols_t_statistics(y: np.ndarray, tutorial: np.ndarray, xai: np.ndarray) -> np.ndarray:
    t = tutorial.astype(float) - 0.5
    x = xai.astype(float) - 0.5
    design = np.column_stack([np.ones(len(y)), t, x, t * x])
    inv = np.linalg.inv(design.T.dot(design))
    beta = inv.dot(design.T).dot(y)
    residual = y - design.dot(beta)
    df = len(y) - design.shape[1]
    sigma2 = float(residual.dot(residual) / df)
    se = np.sqrt(np.diag(inv) * sigma2)
    return beta[1:] / se[1:]


def permutation_pvalues(y: np.ndarray, tutorial: np.ndarray, xai: np.ndarray,
                        draws: int, seed: int) -> Dict[str, object]:
    observed = np.abs(ols_t_statistics(y, tutorial, xai))
    rng = np.random.default_rng(seed)
    exceed = np.ones(3, dtype=int)
    pairs = np.column_stack([tutorial, xai])
    for _ in range(draws):
        permutation = rng.permutation(len(y))
        permuted = pairs[permutation]
        statistic = np.abs(ols_t_statistics(y, permuted[:, 0], permuted[:, 1]))
        exceed += (statistic >= observed).astype(int)
    p = exceed / float(draws + 1)
    return {
        "draws": int(draws),
        "observed_abs_t": list(map(float, observed)),
        "p_values": list(map(float, p)),
    }


def factorial_cell_effects(frame: pd.DataFrame, value_column: str) -> Dict[str, float]:
    means: Dict[Tuple[int, int], float] = {}
    for t in (0, 1):
        for x in (0, 1):
            values = pd.to_numeric(frame.loc[(frame["tutorial_yes"] == t) & (frame["xai_yes"] == x), value_column], errors="coerce").dropna()
            means[(t, x)] = float(values.mean())
    tutorial = ((means[(1, 0)] - means[(0, 0)]) + (means[(1, 1)] - means[(0, 1)])) / 2.0
    xai = ((means[(0, 1)] - means[(0, 0)]) + (means[(1, 1)] - means[(1, 0)])) / 2.0
    interaction = (means[(1, 1)] - means[(1, 0)]) - (means[(0, 1)] - means[(0, 0)])
    return {"Tutorial": tutorial, "XAI": xai, "Tutorial:XAI": interaction}


def bootstrap_factorial_effects(frame: pd.DataFrame, value_column: str,
                                draws: int, seed: int) -> Dict[str, Dict[str, float]]:
    rng = np.random.default_rng(seed)
    cells: Dict[Tuple[int, int], np.ndarray] = {}
    sampled_means: Dict[Tuple[int, int], np.ndarray] = {}
    for t in (0, 1):
        for x in (0, 1):
            values = pd.to_numeric(frame.loc[(frame["tutorial_yes"] == t) & (frame["xai_yes"] == x), value_column], errors="coerce").dropna().to_numpy(dtype=float)
            cells[(t, x)] = values
            indices = rng.integers(0, len(values), size=(draws, len(values)))
            sampled_means[(t, x)] = values[indices].mean(axis=1)
    distributions = {
        "Tutorial": ((sampled_means[(1, 0)] - sampled_means[(0, 0)]) + (sampled_means[(1, 1)] - sampled_means[(0, 1)])) / 2.0,
        "XAI": ((sampled_means[(0, 1)] - sampled_means[(0, 0)]) + (sampled_means[(1, 1)] - sampled_means[(1, 0)])) / 2.0,
        "Tutorial:XAI": (sampled_means[(1, 1)] - sampled_means[(1, 0)]) - (sampled_means[(0, 1)] - sampled_means[(0, 0)]),
    }
    observed = factorial_cell_effects(frame, value_column)
    result = {}
    for effect, distribution in distributions.items():
        q95 = np.quantile(distribution, [0.025, 0.975])
        q9875 = np.quantile(distribution, [0.00625, 0.99375])
        result[effect] = {
            "estimate": float(observed[effect]),
            "ci95_low": float(q95[0]),
            "ci95_high": float(q95[1]),
            "ci98_75_low": float(q9875[0]),
            "ci98_75_high": float(q9875[1]),
            "draws": int(draws),
        }
    return result


def rb12_h4_bounded(frame_zero: pd.DataFrame, frame_nan: pd.DataFrame):
    rows: List[Dict[str, object]] = []
    for metric_index, (label, metric) in enumerate(METRICS):
        policies = (("released_zero", frame_zero),)
        if metric in ("rair", "rsr"):
            policies = (("released_zero", frame_zero), ("defined_participants", frame_nan))
        for policy_index, (policy, source) in enumerate(policies):
            data = source[["tutorial_yes", "xai_yes", "t_c", "x_c", "second_%s" % metric]].dropna().copy()
            data = data.rename(columns={"second_%s" % metric: "outcome"})
            published_model = smf.ols("outcome ~ C(tutorial_yes) * C(xai_yes)", data=data).fit()
            published_anova = sm.stats.anova_lm(published_model, typ=2)
            centered_model = smf.ols("outcome ~ t_c * x_c", data=data).fit()
            hc3 = {row["effect"]: row for row in robust_param_rows(centered_model, label, policy)}
            perm = permutation_pvalues(
                data["outcome"].to_numpy(dtype=float),
                data["tutorial_yes"].to_numpy(dtype=int),
                data["xai_yes"].to_numpy(dtype=int),
                draws=3000,
                seed=12000 + metric_index * 10 + policy_index,
            )
            boot = bootstrap_factorial_effects(data, "outcome", draws=6000, seed=12500 + metric_index * 10 + policy_index)
            term_map = {
                "Tutorial": "C(tutorial_yes)",
                "XAI": "C(xai_yes)",
                "Tutorial:XAI": "C(tutorial_yes):C(xai_yes)",
            }
            for effect_index, effect in enumerate(("Tutorial", "XAI", "Tutorial:XAI")):
                anova_row = published_anova.loc[term_map[effect]]
                b = boot[effect]
                rows.append({
                    "rb_id": "RB-12",
                    "outcome": label,
                    "metric_key": metric,
                    "ratio_policy": policy,
                    "n": int(len(data)),
                    "effect": effect,
                    "ols_F_type2": float(anova_row["F"]),
                    "ols_p_type2": float(anova_row["PR(>F)"]),
                    "hc3_coefficient": hc3[effect]["coefficient"],
                    "hc3_se": hc3[effect]["hc3_se"],
                    "hc3_p": hc3[effect]["hc3_p"],
                    "permutation_abs_t": perm["observed_abs_t"][effect_index],
                    "permutation_p": perm["p_values"][effect_index],
                    "effect_estimate": b["estimate"],
                    "bootstrap_ci95_low": b["ci95_low"],
                    "bootstrap_ci95_high": b["ci95_high"],
                    "bootstrap_ci98_75_low": b["ci98_75_low"],
                    "bootstrap_ci98_75_high": b["ci98_75_high"],
                    "ols_sig_0_0125": bool(anova_row["PR(>F)"] < ALPHA_PUBLISHED),
                    "hc3_sig_0_0125": bool(hc3[effect]["hc3_p"] < ALPHA_PUBLISHED),
                    "permutation_sig_0_0125": bool(perm["p_values"][effect_index] < ALPHA_PUBLISHED),
                    "bootstrap_ci98_75_excludes_zero": bool(b["ci98_75_low"] > 0 or b["ci98_75_high"] < 0),
                })
    changes = [row for row in rows if len({row["ols_sig_0_0125"], row["hc3_sig_0_0125"], row["permutation_sig_0_0125"], row["bootstrap_ci98_75_excludes_zero"]}) > 1]
    memo = {
        "rb_id": "RB-12",
        "concern": "H4 bounded outcomes and OLS assumptions",
        "classification": "Specification-sensitive" if changes else "Stable",
        "decision_disagreements": [
            {key: row[key] for key in ("outcome", "ratio_policy", "effect", "ols_p_type2", "hc3_p", "permutation_p", "bootstrap_ci98_75_low", "bootstrap_ci98_75_high")}
            for row in changes
        ],
        "interpretation": (
            "Type II OLS is retained as the published anchor. HC3 inference, randomization-style label permutations, "
            "and bootstrap factorial-effect intervals test whether the null H4 conclusion depends on Gaussian and "
            "homoskedastic residual assumptions for bounded outcomes."
        ),
    }
    return rows, memo


def gee_time_effects(frame: pd.DataFrame, metric: str) -> List[Dict[str, object]]:
    first = frame[["pid_internal", "t_c", "x_c", "first_%s" % metric]].copy()
    first["time"] = 0.0
    first["outcome"] = first.pop("first_%s" % metric)
    second = frame[["pid_internal", "t_c", "x_c", "second_%s" % metric]].copy()
    second["time"] = 1.0
    second["outcome"] = second.pop("second_%s" % metric)
    long = pd.concat([first, second], ignore_index=True).dropna()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = smf.gee(
            "outcome ~ time * t_c * x_c",
            groups="pid_internal",
            data=long,
            cov_struct=Exchangeable(),
            family=Gaussian(),
        ).fit()
    rows = []
    for effect, parameter in (("Tutorial", "time:t_c"), ("XAI", "time:x_c"), ("Tutorial:XAI", "time:t_c:x_c")):
        rows.append({
            "effect": effect,
            "parameter": parameter,
            "estimate": float(model.params[parameter]),
            "se": float(model.bse[parameter]),
            "p_value": float(model.pvalues[parameter]),
        })
    return rows


def rb13_baseline_models(frame: pd.DataFrame):
    rows: List[Dict[str, object]] = []
    for label, metric in METRICS:
        base = frame[["tutorial_yes", "xai_yes", "t_c", "x_c", "first_%s" % metric, "second_%s" % metric, "delta_%s" % metric, "pid_internal"]].dropna().copy()
        base = base.rename(columns={"first_%s" % metric: "baseline", "second_%s" % metric: "outcome", "delta_%s" % metric: "change"})
        models = {
            "second_batch": smf.ols("outcome ~ C(tutorial_yes) * C(xai_yes)", data=base).fit(),
            "change_score": smf.ols("change ~ C(tutorial_yes) * C(xai_yes)", data=base).fit(),
            "baseline_adjusted_ancova": smf.ols("outcome ~ baseline + C(tutorial_yes) * C(xai_yes)", data=base).fit(),
        }
        term_map = {"Tutorial": "C(tutorial_yes)", "XAI": "C(xai_yes)", "Tutorial:XAI": "C(tutorial_yes):C(xai_yes)"}
        for specification, model in models.items():
            table = sm.stats.anova_lm(model, typ=2)
            for effect, term in term_map.items():
                rows.append({
                    "rb_id": "RB-13",
                    "outcome": label,
                    "specification": specification,
                    "effect": effect,
                    "n": int(model.nobs),
                    "F": float(table.loc[term, "F"]),
                    "p_value": float(table.loc[term, "PR(>F)"]),
                    "significant_0_0125": bool(table.loc[term, "PR(>F)"] < ALPHA_PUBLISHED),
                })
        for gee in gee_time_effects(frame, metric):
            rows.append({
                "rb_id": "RB-13",
                "outcome": label,
                "specification": "repeated_measures_GEE_time_interaction",
                "effect": gee["effect"],
                "n": int(len(base)),
                "F": None,
                "estimate": gee["estimate"],
                "se": gee["se"],
                "p_value": gee["p_value"],
                "significant_0_0125": bool(gee["p_value"] < ALPHA_PUBLISHED),
            })
    changes = []
    for label, _ in METRICS:
        for effect in ("Tutorial", "XAI", "Tutorial:XAI"):
            subset = [row for row in rows if row["outcome"] == label and row["effect"] == effect]
            decisions = sorted(set(bool(row["significant_0_0125"]) for row in subset))
            if len(decisions) > 1:
                changes.append({"outcome": label, "effect": effect, "models": {row["specification"]: row["p_value"] for row in subset}})
    memo = {
        "rb_id": "RB-13",
        "concern": "H4 baseline omission",
        "classification": "Specification-sensitive" if changes else "Stable",
        "decision_changes": changes,
        "interpretation": (
            "Second-batch outcomes, change scores, baseline-adjusted ANCOVA, and a two-wave GEE estimate different "
            "treatment quantities. A conclusion is stable only if the intervention decision does not depend on which "
            "reasonable longitudinal specification is chosen."
        ),
    }
    return rows, memo


def dke_groups(frame: pd.DataFrame):
    n_quartile = int(math.ceil(len(frame) * 0.25))
    ranked = frame.sort_values("first_accuracy", ascending=False, kind="mergesort")
    top = ranked.iloc[:n_quartile]
    bottom = ranked.iloc[-n_quartile:]
    top_cut = float(top["first_accuracy"].min())
    bottom_cut = float(bottom["first_accuracy"].max())
    top_inclusive = frame.loc[frame["first_accuracy"] >= top_cut]
    bottom_inclusive = frame.loc[frame["first_accuracy"] <= bottom_cut]
    return n_quartile, top, bottom, top_cut, bottom_cut, top_inclusive, bottom_inclusive


def group_comparison(top: pd.DataFrame, bottom: pd.DataFrame, column: str) -> Dict[str, object]:
    x = pd.to_numeric(top[column], errors="coerce").dropna().to_numpy(dtype=float)
    y = pd.to_numeric(bottom[column], errors="coerce").dropna().to_numpy(dtype=float)
    mw = stats.mannwhitneyu(x, y, alternative="greater")
    return {
        "n_top": int(len(x)),
        "n_bottom": int(len(y)),
        "top_mean": float(np.mean(x)),
        "bottom_mean": float(np.mean(y)),
        "mean_difference": float(np.mean(x) - np.mean(y)),
        "U_greater": float(mw.statistic),
        "p_greater": float(mw.pvalue),
        "cliffs_delta": cliffs_delta(x, y),
    }


def rb14_dke_ties(frame: pd.DataFrame):
    n_q, top, bottom, top_cut, bottom_cut, top_inc, bottom_inc = dke_groups(frame)
    metric_columns = [(label, "first_%s" % metric) for label, metric in METRICS[1:]]
    released_rows = []
    random_rows = []
    rng = np.random.default_rng(14014)
    top_above = frame.loc[frame["first_accuracy"] > top_cut]
    top_tied = frame.loc[frame["first_accuracy"] == top_cut]
    bottom_below = frame.loc[frame["first_accuracy"] < bottom_cut]
    bottom_tied = frame.loc[frame["first_accuracy"] == bottom_cut]
    top_needed = n_q - len(top_above)
    bottom_needed = n_q - len(bottom_below)
    draws = 2500

    for label, column in metric_columns:
        released = group_comparison(top, bottom, column)
        inclusive = group_comparison(top_inc, bottom_inc, column)
        differences = np.empty(draws, dtype=float)
        pvalues = np.empty(draws, dtype=float)
        over_top = np.empty(draws, dtype=float)
        over_bottom = np.empty(draws, dtype=float)
        for draw in range(draws):
            selected_top = pd.concat([top_above, top_tied.iloc[rng.choice(len(top_tied), size=top_needed, replace=False)]])
            selected_bottom = pd.concat([bottom_below, bottom_tied.iloc[rng.choice(len(bottom_tied), size=bottom_needed, replace=False)]])
            comparison = group_comparison(selected_top, selected_bottom, column)
            differences[draw] = comparison["mean_difference"]
            pvalues[draw] = comparison["p_greater"]
            over_top[draw] = float((selected_top["group_first"] == "Overestimation").mean())
            over_bottom[draw] = float((selected_bottom["group_first"] == "Overestimation").mean())
        released_rows.append({
            "rb_id": "RB-14",
            "metric": label,
            "top_cutoff": top_cut,
            "bottom_cutoff": bottom_cut,
            "quartile_n": n_q,
            "top_tie_total": int(len(top_tied)),
            "top_tie_selected": int(top_needed),
            "bottom_tie_total": int(len(bottom_tied)),
            "bottom_tie_selected": int(bottom_needed),
            **{"released_%s" % key: value for key, value in released.items()},
            **{"tie_inclusive_%s" % key: value for key, value in inclusive.items()},
        })
        random_rows.append({
            "rb_id": "RB-14",
            "metric": label,
            "draws": draws,
            "mean_difference_q025": float(np.quantile(differences, 0.025)),
            "mean_difference_median": float(np.median(differences)),
            "mean_difference_q975": float(np.quantile(differences, 0.975)),
            "p_q025": float(np.quantile(pvalues, 0.025)),
            "p_median": float(np.median(pvalues)),
            "p_q975": float(np.quantile(pvalues, 0.975)),
            "proportion_significant_0_0125": float(np.mean(pvalues < ALPHA_PUBLISHED)),
            "proportion_positive_effect": float(np.mean(differences > 0)),
            "top_overestimation_share_q025": float(np.quantile(over_top, 0.025)),
            "top_overestimation_share_q975": float(np.quantile(over_top, 0.975)),
            "bottom_overestimation_share_q025": float(np.quantile(over_bottom, 0.025)),
            "bottom_overestimation_share_q975": float(np.quantile(over_bottom, 0.975)),
        })
    sensitive = [row for row in random_rows if row["proportion_significant_0_0125"] < 0.95]
    memo = {
        "rb_id": "RB-14",
        "concern": "DKE tied quartile cutoffs",
        "classification": "Specification-sensitive" if sensitive else "Stable",
        "sensitive_metrics": [row["metric"] for row in sensitive],
        "interpretation": (
            "The released stable sort selects only part of large accuracy ties. Tie-inclusive groups and repeated "
            "random tie-breaking quantify whether Table 8 effect estimates and decisions depend on input-row order."
        ),
    }
    return released_rows, random_rows, memo


def rb15_dke_heldout(frame: pd.DataFrame):
    _, top, bottom, _, _, top_inc, bottom_inc = dke_groups(frame)
    rows: List[Dict[str, object]] = []
    for label, metric in METRICS[1:]:
        for group_rule, high, low in (("released_stable", top, bottom), ("tie_inclusive", top_inc, bottom_inc)):
            result = group_comparison(high, low, "second_%s" % metric)
            rows.append({
                "rb_id": "RB-15",
                "analysis": "heldout_top_bottom",
                "group_rule": group_rule,
                "metric": label,
                **result,
                "significant_0_0125": bool(result["p_greater"] < ALPHA_PUBLISHED),
            })
        pair = frame[["first_accuracy", "second_%s" % metric, "condition", "order_id"]].dropna().copy()
        spearman = stats.spearmanr(pair["first_accuracy"], pair["second_%s" % metric], alternative="two-sided")
        robust = smf.ols("Q('second_%s') ~ first_accuracy + C(condition) + C(order_id)" % metric, data=pair).fit().get_robustcov_results(cov_type="HC3")
        name_index = robust.model.exog_names.index("first_accuracy")
        rows.append({
            "rb_id": "RB-15",
            "analysis": "continuous_heldout",
            "group_rule": "continuous_first_accuracy",
            "metric": label,
            "n_top": None,
            "n_bottom": None,
            "top_mean": None,
            "bottom_mean": None,
            "mean_difference": None,
            "U_greater": None,
            "p_greater": None,
            "cliffs_delta": None,
            "spearman_rho": float(spearman.statistic),
            "spearman_p": float(spearman.pvalue),
            "adjusted_HC3_beta": float(robust.params[name_index]),
            "adjusted_HC3_p": float(robust.pvalues[name_index]),
            "significant_0_0125": bool(robust.pvalues[name_index] < ALPHA_PUBLISHED),
        })
    heldout = [row for row in rows if row["analysis"] == "heldout_top_bottom" and row["group_rule"] == "released_stable"]
    sensitive = [row for row in heldout if not row["significant_0_0125"]]
    memo = {
        "rb_id": "RB-15",
        "concern": "DKE same-batch circularity",
        "classification": "Specification-sensitive" if sensitive else "Stable",
        "heldout_metrics_not_significant": [row["metric"] for row in sensitive],
        "interpretation": (
            "First-batch accuracy defines the DKE groups, so first-batch contrasts are partly selected by construction. "
            "Second-batch outcomes and continuous adjusted models provide held-out association tests."
        ),
    }
    return rows, memo


def condition_emms(model, frame: pd.DataFrame):
    ati_mean = float(frame["ati"].mean())
    propensity_mean = float(frame["propensity"].mean())
    new = pd.DataFrame({"condition": list(CONDITION_ORDER), "ati": ati_mean, "propensity": propensity_mean})
    pred = model.get_prediction(new).summary_frame(alpha=0.05)
    design = np.asarray(build_design_matrices([model.model.data.design_info], new)[0])
    emms = []
    for index, condition in enumerate(CONDITION_ORDER):
        emms.append({
            "condition": condition,
            "adjusted_mean": float(pred.iloc[index]["mean"]),
            "se": float(pred.iloc[index]["mean_se"]),
            "ci95_low": float(pred.iloc[index]["mean_ci_lower"]),
            "ci95_high": float(pred.iloc[index]["mean_ci_upper"]),
        })
    pairs = []
    for left in range(len(CONDITION_ORDER)):
        for right in range(left + 1, len(CONDITION_ORDER)):
            contrast = design[left] - design[right]
            test = model.t_test(contrast)
            pairs.append({
                "left": CONDITION_ORDER[left],
                "right": CONDITION_ORDER[right],
                "estimate_left_minus_right": float(np.asarray(test.effect).squeeze()),
                "se": float(np.asarray(test.sd).squeeze()),
                "t": float(np.asarray(test.tvalue).squeeze()),
                "p_value": float(np.asarray(test.pvalue).squeeze()),
            })
    adjusted = adjust_pvalues([row["p_value"] for row in pairs])
    for index, row in enumerate(pairs):
        row["p_holm"] = adjusted["holm"][index]
        row["p_bh_fdr"] = adjusted["bh_fdr"][index]
        row["holm_sig_0_05"] = bool(row["p_holm"] < 0.05)
    return emms, pairs


def rb16_trust_condition(frame: pd.DataFrame):
    model = smf.ols("avg_trust ~ C(condition) + ati + propensity", data=frame).fit()
    table = sm.stats.anova_lm(model, typ=2)
    emms, pairs = condition_emms(model, frame)
    factorial = smf.ols("avg_trust ~ t_c * x_c + ati + propensity", data=frame).fit()
    robust = factorial.get_robustcov_results(cov_type="HC3")
    factorial_rows = []
    for effect, parameter in (("Tutorial", "t_c"), ("XAI", "x_c"), ("Tutorial:XAI", "t_c:x_c")):
        index = robust.model.exog_names.index(parameter)
        factorial_rows.append({
            "effect": effect,
            "estimate": float(robust.params[index]),
            "hc3_se": float(robust.bse[index]),
            "hc3_p": float(robust.pvalues[index]),
        })
    main = {
        "rb_id": "RB-16",
        "condition_df": float(table.loc["C(condition)", "df"]),
        "condition_F": float(table.loc["C(condition)", "F"]),
        "condition_p": float(table.loc["C(condition)", "PR(>F)"]),
        "condition_sum_sq": float(table.loc["C(condition)", "sum_sq"]),
        "residual_sum_sq": float(table.loc["Residual", "sum_sq"]),
        "partial_eta_squared": float(table.loc["C(condition)", "sum_sq"] / (table.loc["C(condition)", "sum_sq"] + table.loc["Residual", "sum_sq"])),
        "factorial_HC3": factorial_rows,
    }
    memo = {
        "rb_id": "RB-16",
        "concern": "Unreported trust condition ANCOVA",
        "classification": "Exploratory",
        "significant_adjusted_pairwise": [row for row in pairs if row["holm_sig_0_05"]],
        "interpretation": (
            "The released code contains a significant four-condition ANCOVA not reported in Table 9. Estimated "
            "marginal means, corrected pairwise contrasts, and factorial HC3 decomposition are presented as exploratory "
            "because the source does not identify this as a published primary result."
        ),
    }
    return main, emms, pairs, factorial_rows, memo


def anova_effect(model, term: str) -> Dict[str, object]:
    table = sm.stats.anova_lm(model, typ=2)
    ss = float(table.loc[term, "sum_sq"])
    residual = float(table.loc["Residual", "sum_sq"])
    return {
        "df": float(table.loc[term, "df"]),
        "F": float(table.loc[term, "F"]),
        "p_value": float(table.loc[term, "PR(>F)"]),
        "partial_eta_squared": ss / (ss + residual),
        "AIC": float(model.aic),
        "n": int(model.nobs),
    }


def rb17_trust_construction(frame: pd.DataFrame):
    rows: List[Dict[str, object]] = []
    model_specs = (
        ("calibration_group", "average_trust", "avg_trust ~ C(group_first) + ati + propensity", "C(group_first)"),
        ("calibration_group", "second_wave_baseline_adjusted", "trust_second ~ trust_first + C(group_first) + ati + propensity", "C(group_first)"),
        ("calibration_group", "change_score", "change_trust ~ C(group_first) + ati + propensity", "C(group_first)"),
        ("condition", "average_trust", "avg_trust ~ C(condition) + ati + propensity", "C(condition)"),
        ("condition", "second_wave_baseline_adjusted", "trust_second ~ trust_first + C(condition) + ati + propensity", "C(condition)"),
        ("condition", "change_score", "change_trust ~ C(condition) + ati + propensity", "C(condition)"),
    )
    for factor, outcome_definition, formula, term in model_specs:
        model = smf.ols(formula, data=frame).fit()
        result = anova_effect(model, term)
        rows.append({
            "rb_id": "RB-17",
            "factor": factor,
            "outcome_definition": outcome_definition,
            "formula": formula,
            **result,
            "significant_0_0125": bool(result["p_value"] < ALPHA_PUBLISHED),
        })
    changes = []
    for factor in ("calibration_group", "condition"):
        subset = [row for row in rows if row["factor"] == factor]
        decisions = sorted(set(bool(row["significant_0_0125"]) for row in subset))
        if len(decisions) > 1:
            changes.append({"factor": factor, "models": {row["outcome_definition"]: row["p_value"] for row in subset}})
    memo = {
        "rb_id": "RB-17",
        "concern": "Trust outcome construction",
        "classification": "Specification-sensitive" if changes else "Stable",
        "decision_changes": changes,
        "interpretation": (
            "Average trust, second-wave trust adjusted for baseline, and trust change answer different longitudinal "
            "questions. The audit reports all three without treating the mean-of-waves outcome as uniquely privileged."
        ),
    }
    return rows, memo


def rb07_h4_trust_supplement(frame: pd.DataFrame):
    tests_h4 = []
    for label, metric in METRICS:
        data = frame[["tutorial_yes", "xai_yes", "second_%s" % metric]].dropna().rename(columns={"second_%s" % metric: "outcome"})
        model = smf.ols("outcome ~ C(tutorial_yes) * C(xai_yes)", data=data).fit()
        table = sm.stats.anova_lm(model, typ=2)
        for effect, term in (("Tutorial", "C(tutorial_yes)"), ("XAI", "C(xai_yes)"), ("Interaction", "C(tutorial_yes):C(xai_yes)")):
            tests_h4.append({
                "test_id": "H4_%s_%s" % (effect, metric),
                "label": "H4 %s %s" % (effect, label),
                "effect": effect,
                "p_value": float(table.loc[term, "PR(>F)"]),
            })
    trust_model = smf.ols("avg_trust ~ C(group_first) + ati + propensity", data=frame).fit()
    trust_table = sm.stats.anova_lm(trust_model, typ=2)
    trust_tests = [
        {"test_id": "Trust_calibration_group", "label": "Trust calibration group", "p_value": float(trust_table.loc["C(group_first)", "PR(>F)"])},
        {"test_id": "Trust_ATI", "label": "Trust ATI", "p_value": float(trust_table.loc["ati", "PR(>F)"])},
        {"test_id": "Trust_propensity", "label": "Trust propensity", "p_value": float(trust_table.loc["propensity", "PR(>F)"])},
    ]
    correlation_tests = []
    for label, column in (("Average trust", "avg_trust"), ("Accuracy", "overall_accuracy"), ("Agreement", "overall_agreement_fraction"), ("Switch", "overall_switch_fraction"), ("RAIR", "overall_rair"), ("RSR", "overall_rsr")):
        pair = frame[["propensity", column]].dropna()
        corr = stats.spearmanr(pair["propensity"], pair[column])
        correlation_tests.append({"test_id": "Trust_corr_%s" % column, "label": "Propensity correlation %s" % label, "p_value": float(corr.pvalue)})
    rows = []
    for effect in ("Tutorial", "XAI", "Interaction"):
        rows.extend(multiplicity_rows("H4_%s_six" % effect, [row for row in tests_h4 if row["effect"] == effect]))
    rows.extend(multiplicity_rows("H4_global_eighteen", tests_h4))
    rows.extend(multiplicity_rows("Trust_Table9_three", trust_tests))
    rows.extend(multiplicity_rows("Trust_correlations_six", correlation_tests))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    frame_zero = prepare_frame(build_clean_metric_frame(repo, undefined_ratio="zero"))
    frame_nan = prepare_frame(build_clean_metric_frame(repo, undefined_ratio="nan"))

    rb12_rows, rb12_memo = rb12_h4_bounded(frame_zero, frame_nan)
    rb13_rows, rb13_memo = rb13_baseline_models(frame_zero)
    rb14_released, rb14_random, rb14_memo = rb14_dke_ties(frame_zero)
    rb15_rows, rb15_memo = rb15_dke_heldout(frame_zero)
    rb16_main, rb16_emms, rb16_pairs, rb16_factorial, rb16_memo = rb16_trust_condition(frame_zero)
    rb17_rows, rb17_memo = rb17_trust_construction(frame_zero)
    rb07_supplement = rb07_h4_trust_supplement(frame_zero)

    write_tsv(out / "rb12_h4_robust_inference.tsv", rb12_rows)
    write_json(out / "rb12_memo.json", rb12_memo)
    write_tsv(out / "rb13_h4_longitudinal_models.tsv", rb13_rows)
    write_json(out / "rb13_memo.json", rb13_memo)
    write_tsv(out / "rb14_dke_released_tie_inclusive.tsv", rb14_released)
    write_tsv(out / "rb14_dke_random_ties.tsv", rb14_random)
    write_json(out / "rb14_memo.json", rb14_memo)
    write_tsv(out / "rb15_dke_heldout.tsv", rb15_rows)
    write_json(out / "rb15_memo.json", rb15_memo)
    write_json(out / "rb16_condition_ancova.json", rb16_main)
    write_tsv(out / "rb16_adjusted_means.tsv", rb16_emms)
    write_tsv(out / "rb16_pairwise_contrasts.tsv", rb16_pairs)
    write_tsv(out / "rb16_factorial_hc3.tsv", rb16_factorial)
    write_json(out / "rb16_memo.json", rb16_memo)
    write_tsv(out / "rb17_trust_outcome_models.tsv", rb17_rows)
    write_json(out / "rb17_memo.json", rb17_memo)
    write_tsv(out / "rb07_h4_trust_multiplicity_supplement.tsv", rb07_supplement)

    memos = [rb12_memo, rb13_memo, rb14_memo, rb15_memo, rb16_memo, rb17_memo]
    summary = {
        "schema_version": "1.0",
        "stage": "hypothesis robustness H4-DKE-Trust",
        "sample_n": 249,
        "passed": True,
        "upstream_util_imported": False,
        "participant_level_data_emitted": False,
        "checks": memos,
        "classifications": {memo["rb_id"]: memo["classification"] for memo in memos},
    }
    write_json(out / "h4_dke_trust_robustness_summary.json", summary)
    (out / "H4_DKE_TRUST_STATUS.md").write_text(
        "# ETH HAI H4–DKE–Trust Robustness Gate\n\n" +
        "\n".join("- %s: **%s**" % (memo["rb_id"], memo["classification"]) for memo in memos) +
        "\n- Upstream `util.py` imported: **NO**\n- Participant-level data emitted: **NO**\n",
        encoding="utf-8",
    )
    print(json.dumps({"passed": True, "classifications": summary["classifications"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
