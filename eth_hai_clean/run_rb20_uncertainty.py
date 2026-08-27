#!/usr/bin/env python3
"""RB-20 comprehensive uncertainty reporting.

The output is an aggregate-only appendix of confidence intervals and standardized
effect sizes. The script uses the independent clean core and never emits participant
identifiers or participant-level rows.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd
from patsy import build_design_matrices
from scipy import stats
import statsmodels.api as sm
import statsmodels.formula.api as smf

from eth_hai_clean.core import build_clean_metric_frame
from eth_hai_clean.hypothesis_common import (
    ALPHA_PUBLISHED,
    CALIBRATION_ORDER,
    CONDITION_ORDER,
    METRICS,
    adjust_pvalues,
    calibration_label,
    cliffs_delta,
    epsilon_squared_kruskal,
    rank_biserial_paired,
    write_json,
    write_tsv,
)

DRAWS = 10000
TUTORIAL_RAW = 0


def prepare(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy().reset_index(drop=True)
    out["group_first"] = out["miscalibration_first"].astype(float).map(calibration_label)
    out["tutorial_yes"] = 1 - out["tutorial_raw"].astype(int)
    out["xai_yes"] = out["xai_raw"].astype(int)
    out["t_c"] = out["tutorial_yes"].astype(float) - 0.5
    out["x_c"] = out["xai_yes"].astype(float) - 0.5
    out["avg_trust"] = (out["trust_first"] + out["trust_second"]) / 2.0
    out["change_trust"] = out["trust_second"] - out["trust_first"]
    for _, metric in METRICS:
        out["delta_%s" % metric] = out["second_%s" % metric] - out["first_%s" % metric]
    return out


def percentile_ci(distribution: np.ndarray, level: float = 0.95) -> Tuple[float, float]:
    tail = (1.0 - level) / 2.0
    low, high = np.quantile(distribution, [tail, 1.0 - tail])
    return float(low), float(high)


def paired_bootstrap(values: Sequence[float], draws: int, seed: int) -> Dict[str, float]:
    x = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(x), size=(draws, len(x)))
    samples = x[indices]
    means = samples.mean(axis=1)
    medians = np.median(samples, axis=1)
    mean_low, mean_high = percentile_ci(means)
    median_low, median_high = percentile_ci(medians)
    return {
        "mean": float(x.mean()),
        "mean_ci95_low": mean_low,
        "mean_ci95_high": mean_high,
        "median": float(np.median(x)),
        "median_ci95_low": median_low,
        "median_ci95_high": median_high,
        "draws": int(draws),
    }


def two_sample_bootstrap(x_values: Sequence[float], y_values: Sequence[float], draws: int, seed: int) -> Dict[str, float]:
    x = np.asarray(x_values, dtype=float)
    y = np.asarray(y_values, dtype=float)
    rng = np.random.default_rng(seed)
    ix = rng.integers(0, len(x), size=(draws, len(x)))
    iy = rng.integers(0, len(y), size=(draws, len(y)))
    mean_dist = x[ix].mean(axis=1) - y[iy].mean(axis=1)
    median_dist = np.median(x[ix], axis=1) - np.median(y[iy], axis=1)
    mean_low, mean_high = percentile_ci(mean_dist)
    median_low, median_high = percentile_ci(median_dist)
    pooled_sd = math.sqrt(((len(x) - 1) * np.var(x, ddof=1) + (len(y) - 1) * np.var(y, ddof=1)) / float(len(x) + len(y) - 2))
    return {
        "n_left": int(len(x)),
        "n_right": int(len(y)),
        "left_mean": float(np.mean(x)),
        "right_mean": float(np.mean(y)),
        "mean_difference": float(np.mean(x) - np.mean(y)),
        "mean_difference_ci95_low": mean_low,
        "mean_difference_ci95_high": mean_high,
        "median_difference": float(np.median(x) - np.median(y)),
        "median_difference_ci95_low": median_low,
        "median_difference_ci95_high": median_high,
        "cohens_d": float((np.mean(x) - np.mean(y)) / pooled_sd) if pooled_sd > 0 else 0.0,
        "cliffs_delta": cliffs_delta(x, y),
        "draws": int(draws),
    }


def h1_uncertainty(frame: pd.DataFrame) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    pairs = (("Underestimation", "Accurate"), ("Underestimation", "Overestimation"), ("Accurate", "Overestimation"))
    for metric_index, (label, metric) in enumerate(METRICS):
        value = "second_%s" % metric
        groups = [frame.loc[frame["group_first"] == group, value].dropna().astype(float).to_numpy() for group in CALIBRATION_ORDER]
        kw = stats.kruskal(*groups)
        epsilon = epsilon_squared_kruskal(float(kw.statistic), sum(len(group) for group in groups), 3)
        for pair_index, (left, right) in enumerate(pairs):
            x = frame.loc[frame["group_first"] == left, value].dropna().astype(float).to_numpy()
            y = frame.loc[frame["group_first"] == right, value].dropna().astype(float).to_numpy()
            boot = two_sample_bootstrap(x, y, DRAWS, 20000 + metric_index * 10 + pair_index)
            mw = stats.mannwhitneyu(x, y, alternative="two-sided")
            rows.append({
                "analysis": "H1 held-out",
                "metric": label,
                "left_group": left,
                "right_group": right,
                "omnibus_H": float(kw.statistic),
                "omnibus_p": float(kw.pvalue),
                "omnibus_epsilon_squared": epsilon,
                "mannwhitney_U": float(mw.statistic),
                "mannwhitney_p_two_sided": float(mw.pvalue),
                **boot,
                "mean_ci_excludes_zero": bool(boot["mean_difference_ci95_low"] > 0 or boot["mean_difference_ci95_high"] < 0),
            })
    return rows


def h2_uncertainty(frame: pd.DataFrame) -> List[Dict[str, object]]:
    tutorial = frame.loc[(frame["tutorial_raw"] == TUTORIAL_RAW) & (frame["miscalibration_first"] != 0)].copy()
    rows: List[Dict[str, object]] = []
    for index, (group, subset) in enumerate((
        ("all", tutorial),
        ("under", tutorial.loc[tutorial["miscalibration_first"] < 0]),
        ("over", tutorial.loc[tutorial["miscalibration_first"] > 0]),
    )):
        before = subset["miscalibration_first"].abs().astype(float).to_numpy()
        after = subset["miscalibration_second"].abs().astype(float).to_numpy()
        improvement = before - after
        boot = paired_bootstrap(improvement, DRAWS, 21000 + index)
        wilcox = stats.wilcoxon(before, after, alternative="greater", zero_method="wilcox", correction=False, mode="auto")
        sd = float(np.std(improvement, ddof=1))
        rows.append({
            "analysis": "H2 absolute calibration improvement",
            "group": group,
            "n": int(len(subset)),
            "before_mean": float(np.mean(before)),
            "after_mean": float(np.mean(after)),
            "wilcoxon_W": float(wilcox.statistic),
            "wilcoxon_p_one_sided": float(wilcox.pvalue),
            "cohens_dz_improvement": float(np.mean(improvement) / sd) if sd > 0 else 0.0,
            "paired_rank_biserial_improvement": rank_biserial_paired(after, before),
            **boot,
            "mean_ci_excludes_zero": bool(boot["mean_ci95_low"] > 0 or boot["mean_ci95_high"] < 0),
            "median_ci_excludes_zero": bool(boot["median_ci95_low"] > 0 or boot["median_ci95_high"] < 0),
        })
    return rows


def h3_uncertainty(frame: pd.DataFrame) -> List[Dict[str, object]]:
    tutorial = frame.loc[frame["tutorial_raw"] == TUTORIAL_RAW].copy()
    rows: List[Dict[str, object]] = []
    for group_index, (group, subset, alternative) in enumerate((
        ("under", tutorial.loc[tutorial["miscalibration_first"] < 0], "greater"),
        ("over", tutorial.loc[tutorial["miscalibration_first"] > 0], "less"),
    )):
        for metric_index, (label, metric) in enumerate(METRICS):
            before = subset["first_%s" % metric].astype(float).to_numpy()
            after = subset["second_%s" % metric].astype(float).to_numpy()
            change = after - before
            boot = paired_bootstrap(change, DRAWS, 22000 + group_index * 100 + metric_index)
            wilcox = stats.wilcoxon(before, after, alternative=alternative, zero_method="wilcox", correction=False, mode="auto")
            sd = float(np.std(change, ddof=1))
            rows.append({
                "analysis": "H3 paired outcome change",
                "group": group,
                "metric": label,
                "n": int(len(subset)),
                "expected_alternative": alternative,
                "wilcoxon_W": float(wilcox.statistic),
                "wilcoxon_p_directional": float(wilcox.pvalue),
                "cohens_dz_second_minus_first": float(np.mean(change) / sd) if sd > 0 else 0.0,
                "paired_rank_biserial_second_minus_first": rank_biserial_paired(before, after),
                **boot,
                "mean_ci_excludes_zero": bool(boot["mean_ci95_low"] > 0 or boot["mean_ci95_high"] < 0),
            })
    return rows


def factorial_effects(frame: pd.DataFrame, column: str, draws: int, seed: int) -> Dict[str, Dict[str, float]]:
    rng = np.random.default_rng(seed)
    sampled: Dict[Tuple[int, int], np.ndarray] = {}
    observed: Dict[Tuple[int, int], float] = {}
    for t in (0, 1):
        for x in (0, 1):
            values = frame.loc[(frame["tutorial_yes"] == t) & (frame["xai_yes"] == x), column].dropna().astype(float).to_numpy()
            observed[(t, x)] = float(np.mean(values))
            indices = rng.integers(0, len(values), size=(draws, len(values)))
            sampled[(t, x)] = values[indices].mean(axis=1)
    estimates = {
        "Tutorial": ((observed[(1, 0)] - observed[(0, 0)]) + (observed[(1, 1)] - observed[(0, 1)])) / 2.0,
        "XAI": ((observed[(0, 1)] - observed[(0, 0)]) + (observed[(1, 1)] - observed[(1, 0)])) / 2.0,
        "Tutorial:XAI": (observed[(1, 1)] - observed[(1, 0)]) - (observed[(0, 1)] - observed[(0, 0)]),
    }
    distributions = {
        "Tutorial": ((sampled[(1, 0)] - sampled[(0, 0)]) + (sampled[(1, 1)] - sampled[(0, 1)])) / 2.0,
        "XAI": ((sampled[(0, 1)] - sampled[(0, 0)]) + (sampled[(1, 1)] - sampled[(1, 0)])) / 2.0,
        "Tutorial:XAI": (sampled[(1, 1)] - sampled[(1, 0)]) - (sampled[(0, 1)] - sampled[(0, 0)]),
    }
    output: Dict[str, Dict[str, float]] = {}
    for effect in ("Tutorial", "XAI", "Tutorial:XAI"):
        low95, high95 = percentile_ci(distributions[effect], 0.95)
        low9875, high9875 = percentile_ci(distributions[effect], 0.9875)
        output[effect] = {
            "estimate": float(estimates[effect]),
            "ci95_low": low95,
            "ci95_high": high95,
            "ci98_75_low": low9875,
            "ci98_75_high": high9875,
        }
    return output


def h4_uncertainty(frame: pd.DataFrame) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    term_map = {"Tutorial": "C(tutorial_yes)", "XAI": "C(xai_yes)", "Tutorial:XAI": "C(tutorial_yes):C(xai_yes)"}
    for metric_index, (label, metric) in enumerate(METRICS):
        value = "second_%s" % metric
        data = frame[["tutorial_yes", "xai_yes", value]].dropna().copy()
        model = smf.ols("Q('%s') ~ C(tutorial_yes) * C(xai_yes)" % value, data=data).fit()
        table = sm.stats.anova_lm(model, typ=2)
        boot = factorial_effects(data, value, DRAWS, 23000 + metric_index)
        outcome_sd = float(data[value].std(ddof=1))
        residual_ss = float(table.loc["Residual", "sum_sq"])
        for effect in ("Tutorial", "XAI", "Tutorial:XAI"):
            term = term_map[effect]
            ss = float(table.loc[term, "sum_sq"])
            b = boot[effect]
            rows.append({
                "analysis": "H4 factorial uncertainty",
                "metric": label,
                "effect": effect,
                "n": int(len(data)),
                "F_type2": float(table.loc[term, "F"]),
                "p_type2": float(table.loc[term, "PR(>F)"]),
                "partial_eta_squared": float(ss / (ss + residual_ss)),
                "standardized_effect_outcome_sd": float(b["estimate"] / outcome_sd) if outcome_sd > 0 else 0.0,
                **b,
                "ci98_75_excludes_zero": bool(b["ci98_75_low"] > 0 or b["ci98_75_high"] < 0),
            })
    return rows


def stable_quartiles(frame: pd.DataFrame):
    n_q = int(math.ceil(len(frame) * 0.25))
    ranked = frame.sort_values("first_accuracy", ascending=False, kind="mergesort")
    return ranked.iloc[:n_q], ranked.iloc[-n_q:]


def dke_uncertainty(frame: pd.DataFrame) -> List[Dict[str, object]]:
    top, bottom = stable_quartiles(frame)
    rows: List[Dict[str, object]] = []
    for index, (label, metric) in enumerate(METRICS[1:]):
        x = top["second_%s" % metric].dropna().astype(float).to_numpy()
        y = bottom["second_%s" % metric].dropna().astype(float).to_numpy()
        boot = two_sample_bootstrap(x, y, DRAWS, 24000 + index)
        mw = stats.mannwhitneyu(x, y, alternative="greater")
        rows.append({
            "analysis": "DKE held-out top-bottom uncertainty",
            "metric": label,
            "mannwhitney_U": float(mw.statistic),
            "mannwhitney_p_greater": float(mw.pvalue),
            **boot,
            "mean_ci_excludes_zero": bool(boot["mean_difference_ci95_low"] > 0 or boot["mean_difference_ci95_high"] < 0),
        })
    return rows


def trust_pairwise_uncertainty(frame: pd.DataFrame) -> List[Dict[str, object]]:
    model = smf.ols(
        "trust_second ~ trust_first + C(condition) + ati + propensity + C(order_id)", data=frame
    ).fit()
    robust = model.get_robustcov_results(cov_type="HC3")
    means = {
        "trust_first": float(frame["trust_first"].mean()),
        "ati": float(frame["ati"].mean()),
        "propensity": float(frame["propensity"].mean()),
    }
    grid_rows = []
    for condition in CONDITION_ORDER:
        for order_id in sorted(frame["order_id"].astype(int).unique()):
            grid_rows.append({"condition": condition, "order_id": int(order_id), **means})
    grid = pd.DataFrame(grid_rows)
    design = np.asarray(build_design_matrices([model.model.data.design_info], grid)[0])
    averaged: Dict[str, np.ndarray] = {}
    for index, condition in enumerate(CONDITION_ORDER):
        start = index * frame["order_id"].nunique()
        stop = start + frame["order_id"].nunique()
        averaged[condition] = design[start:stop].mean(axis=0)
    covariance = np.asarray(robust.cov_params())
    residual_sd = float(np.sqrt(model.ssr / model.df_resid))
    rows: List[Dict[str, object]] = []
    pairs = []
    for left_index in range(len(CONDITION_ORDER)):
        for right_index in range(left_index + 1, len(CONDITION_ORDER)):
            left = CONDITION_ORDER[left_index]
            right = CONDITION_ORDER[right_index]
            contrast = averaged[left] - averaged[right]
            estimate = float(np.dot(contrast, robust.params))
            se = float(np.sqrt(np.dot(contrast, np.dot(covariance, contrast))))
            t_value = estimate / se if se > 0 else 0.0
            p_value = float(2.0 * stats.t.sf(abs(t_value), df=robust.df_resid))
            critical = float(stats.t.ppf(0.975, df=robust.df_resid))
            pairs.append({
                "analysis": "Trust baseline-adjusted condition contrast",
                "left": left,
                "right": right,
                "estimate_left_minus_right": estimate,
                "hc3_se": se,
                "t": t_value,
                "p_value": p_value,
                "ci95_low": estimate - critical * se,
                "ci95_high": estimate + critical * se,
                "standardized_estimate_residual_sd": estimate / residual_sd if residual_sd > 0 else 0.0,
            })
    adjusted = adjust_pvalues([row["p_value"] for row in pairs])
    for index, row in enumerate(pairs):
        row["p_holm"] = adjusted["holm"][index]
        row["holm_sig_0_05"] = bool(row["p_holm"] < 0.05)
        row["ci95_excludes_zero"] = bool(row["ci95_low"] > 0 or row["ci95_high"] < 0)
        rows.append(row)
    return rows


def trust_tutorial_uncertainty(frame: pd.DataFrame) -> Dict[str, object]:
    subset = frame.loc[frame["tutorial_raw"] == TUTORIAL_RAW]
    before = subset["trust_first"].astype(float).to_numpy()
    after = subset["trust_second"].astype(float).to_numpy()
    change = after - before
    boot = paired_bootstrap(change, DRAWS, 25000)
    test = stats.wilcoxon(before, after, alternative="two-sided", zero_method="wilcox", correction=False, mode="auto")
    sd = float(np.std(change, ddof=1))
    return {
        "analysis": "Trust tutorial paired change",
        "n": int(len(subset)),
        "before_mean": float(np.mean(before)),
        "after_mean": float(np.mean(after)),
        "wilcoxon_W": float(test.statistic),
        "wilcoxon_p_two_sided": float(test.pvalue),
        "cohens_dz_second_minus_first": float(np.mean(change) / sd) if sd > 0 else 0.0,
        "paired_rank_biserial_second_minus_first": rank_biserial_paired(before, after),
        **boot,
        "mean_ci_excludes_zero": bool(boot["mean_ci95_low"] > 0 or boot["mean_ci95_high"] < 0),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    frame = prepare(build_clean_metric_frame(repo, undefined_ratio="zero"))
    h1 = h1_uncertainty(frame)
    h2 = h2_uncertainty(frame)
    h3 = h3_uncertainty(frame)
    h4 = h4_uncertainty(frame)
    dke = dke_uncertainty(frame)
    trust_pairs = trust_pairwise_uncertainty(frame)
    trust_tutorial = trust_tutorial_uncertainty(frame)

    boundary_h2 = next(row for row in h2 if row["group"] == "over")
    sensitive = bool(
        not boundary_h2["median_ci_excludes_zero"]
        or any(not row["mean_ci_excludes_zero"] for row in dke)
        or any(row["ci98_75_excludes_zero"] for row in h4)
    )
    memo = {
        "rb_id": "RB-20",
        "concern": "Uncertainty reporting",
        "classification": "Specification-sensitive" if sensitive else "Stable",
        "bootstrap_draws_per_result": DRAWS,
        "tables": {
            "H1_pairwise_rows": len(h1),
            "H2_rows": len(h2),
            "H3_rows": len(h3),
            "H4_rows": len(h4),
            "DKE_rows": len(dke),
            "Trust_pairwise_rows": len(trust_pairs),
        },
        "h2_overestimator_mean_ci": [boundary_h2["mean_ci95_low"], boundary_h2["mean_ci95_high"]],
        "h2_overestimator_median_ci": [boundary_h2["median_ci95_low"], boundary_h2["median_ci95_high"]],
        "interpretation": (
            "Confidence intervals and standardized effect sizes are reported beside p-values. The appendix distinguishes "
            "precise nulls, imprecise nulls, and boundary evidence; an interval containing zero is not equated with proof "
            "of no effect, and an interval excluding zero is not treated as a substitute for multiplicity control."
        ),
    }
    summary = {
        "schema_version": "1.0",
        "stage": "RB-20 uncertainty reporting",
        "sample_n": int(len(frame)),
        "passed": True,
        "classification": memo["classification"],
        "memo": memo,
        "upstream_util_imported": False,
        "participant_level_data_emitted": False,
    }

    write_tsv(out / "rb20_h1_heldout_uncertainty.tsv", h1)
    write_tsv(out / "rb20_h2_calibration_uncertainty.tsv", h2)
    write_tsv(out / "rb20_h3_change_uncertainty.tsv", h3)
    write_tsv(out / "rb20_h4_factorial_uncertainty.tsv", h4)
    write_tsv(out / "rb20_dke_heldout_uncertainty.tsv", dke)
    write_tsv(out / "rb20_trust_pairwise_uncertainty.tsv", trust_pairs)
    write_json(out / "rb20_trust_tutorial_uncertainty.json", trust_tutorial)
    write_json(out / "rb20_memo.json", memo)
    write_json(out / "rb20_summary.json", summary)
    (out / "RB20_STATUS.md").write_text(
        "# RB-20 Comprehensive Uncertainty Reporting\n\n"
        "- Execution: **PASS**\n"
        "- Classification: **%s**\n"
        "- Bootstrap draws per result: **%d**\n"
        "- Upstream `util.py` imported: **NO**\n"
        "- Participant-level data emitted: **NO**\n" % (memo["classification"], DRAWS),
        encoding="utf-8",
    )
    print(json.dumps({"passed": True, "classification": memo["classification"], "draws": DRAWS}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
