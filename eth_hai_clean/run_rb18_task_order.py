#!/usr/bin/env python3
"""RB-18 task-order heterogeneity audit.

This module is aggregate-only. It uses the independent clean core, does not import
upstream util.py, and never writes participant identifiers or participant-level rows.
"""
from __future__ import annotations

import argparse
import json
import math
import warnings
from pathlib import Path
from typing import Dict, List, Mapping, Sequence, Tuple

import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.formula.api as smf

from eth_hai_clean.core import build_clean_metric_frame
from eth_hai_clean.hypothesis_common import (
    ALPHA_PUBLISHED,
    CONDITION_ORDER,
    METRICS,
    calibration_label,
    cliffs_delta,
    write_json,
    write_tsv,
)

TUTORIAL_RAW = 0


def prepare_frame(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy().reset_index(drop=True)
    out["group_first"] = out["miscalibration_first"].astype(float).map(calibration_label)
    out["tutorial_yes"] = 1 - out["tutorial_raw"].astype(int)
    out["xai_yes"] = out["xai_raw"].astype(int)
    out["t_c"] = out["tutorial_yes"].astype(float) - 0.5
    out["x_c"] = out["xai_yes"].astype(float) - 0.5
    out["trust_change"] = out["trust_second"] - out["trust_first"]
    for _, metric in METRICS:
        out["delta_%s" % metric] = out["second_%s" % metric] - out["first_%s" % metric]
    return out


def scalar(value) -> float:
    return float(np.asarray(value).squeeze())


def joint_hc3_wald(model, contains: str) -> Dict[str, object]:
    robust = model.get_robustcov_results(cov_type="HC3")
    names = list(model.model.exog_names)
    indices = [index for index, name in enumerate(names) if contains in name]
    if not indices:
        return {"df_num": 0, "df_denom": float(robust.df_resid), "F": None, "p_value": None}
    restriction = np.zeros((len(indices), len(names)), dtype=float)
    for row, index in enumerate(indices):
        restriction[row, index] = 1.0
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = robust.wald_test(restriction, use_f=True)
    return {
        "df_num": int(len(indices)),
        "df_denom": float(robust.df_resid),
        "F": scalar(result.statistic),
        "p_value": scalar(result.pvalue),
    }


def robust_parameter(model, name: str) -> Dict[str, float]:
    robust = model.get_robustcov_results(cov_type="HC3")
    names = list(model.model.exog_names)
    index = names.index(name)
    return {
        "estimate": float(robust.params[index]),
        "se": float(robust.bse[index]),
        "statistic": float(robust.tvalues[index]),
        "p_value": float(robust.pvalues[index]),
    }


def order_distribution(frame: pd.DataFrame) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for order_id in sorted(frame["order_id"].astype(int).unique()):
        subset = frame.loc[frame["order_id"].astype(int) == order_id]
        row: Dict[str, object] = {
            "order_id": int(order_id),
            "participants_n": int(len(subset)),
            "tutorial_yes_n": int((subset["tutorial_yes"] == 1).sum()),
            "xai_yes_n": int((subset["xai_yes"] == 1).sum()),
            "under_n": int((subset["group_first"] == "Underestimation").sum()),
            "accurate_n": int((subset["group_first"] == "Accurate").sum()),
            "over_n": int((subset["group_first"] == "Overestimation").sum()),
        }
        for condition in CONDITION_ORDER:
            row["condition_%s_n" % condition.replace(" ", "_").replace(",", "")] = int((subset["condition"] == condition).sum())
        rows.append(row)
    return rows


def h1_fixed_effects(frame: pd.DataFrame) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for label, metric in METRICS:
        value = "second_%s" % metric
        data = frame[["group_first", "order_id", value]].dropna().copy()
        model = smf.ols("Q('%s') ~ C(group_first) + C(order_id)" % value, data=data).fit()
        group = joint_hc3_wald(model, "C(group_first)")
        order = joint_hc3_wald(model, "C(order_id)")
        rows.append({
            "analysis": "H1 held-out group association",
            "metric": label,
            "n": int(model.nobs),
            "group_F_HC3": group["F"],
            "group_p_HC3": group["p_value"],
            "group_significant_0_0125": bool(group["p_value"] is not None and group["p_value"] < ALPHA_PUBLISHED),
            "order_F_HC3": order["F"],
            "order_p_HC3": order["p_value"],
            "order_significant_0_0125": bool(order["p_value"] is not None and order["p_value"] < ALPHA_PUBLISHED),
        })
    return rows


def wilcoxon_safe(before: Sequence[float], after: Sequence[float], alternative: str) -> Dict[str, object]:
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = stats.wilcoxon(before, after, alternative=alternative, zero_method="wilcox", correction=False, mode="auto")
        return {
            "statistic": float(result.statistic),
            "p_value": float(result.pvalue),
            "warning": " | ".join(str(item.message) for item in caught),
            "error": "",
        }
    except Exception as exc:
        return {"statistic": None, "p_value": None, "warning": "", "error": repr(exc)}


def h2_result(frame: pd.DataFrame, group: str) -> Dict[str, object]:
    subset = frame.loc[(frame["tutorial_raw"].astype(int) == TUTORIAL_RAW) & (frame["miscalibration_first"] != 0)].copy()
    if group == "under":
        subset = subset.loc[subset["miscalibration_first"] < 0]
    elif group == "over":
        subset = subset.loc[subset["miscalibration_first"] > 0]
    before = subset["miscalibration_first"].abs().astype(float).to_numpy()
    after = subset["miscalibration_second"].abs().astype(float).to_numpy()
    result = wilcoxon_safe(before, after, "greater")
    return {
        "n": int(len(subset)),
        "before_mean": float(np.mean(before)) if len(before) else None,
        "after_mean": float(np.mean(after)) if len(after) else None,
        **result,
    }


def h3_result(frame: pd.DataFrame, group: str, metric: str) -> Dict[str, object]:
    tutorial = frame.loc[frame["tutorial_raw"].astype(int) == TUTORIAL_RAW].copy()
    if group == "under":
        subset = tutorial.loc[tutorial["miscalibration_first"] < 0]
        alternative = "greater"
    elif group == "over":
        subset = tutorial.loc[tutorial["miscalibration_first"] > 0]
        alternative = "less"
    else:
        raise ValueError(group)
    before = subset["first_%s" % metric].astype(float).to_numpy()
    after = subset["second_%s" % metric].astype(float).to_numpy()
    result = wilcoxon_safe(before, after, alternative)
    return {
        "n": int(len(subset)),
        "alternative": alternative,
        "mean_change_second_minus_first": float(np.mean(after - before)) if len(before) else None,
        **result,
    }


def h4_result(frame: pd.DataFrame, metric: str) -> Dict[str, Dict[str, object]]:
    value = "second_%s" % metric
    data = frame[["t_c", "x_c", "order_id", value]].dropna().rename(columns={value: "outcome"})
    model = smf.ols("outcome ~ t_c * x_c + C(order_id)", data=data).fit()
    return {
        "Tutorial": robust_parameter(model, "t_c"),
        "XAI": robust_parameter(model, "x_c"),
        "Tutorial:XAI": robust_parameter(model, "t_c:x_c"),
        "Order": joint_hc3_wald(model, "C(order_id)"),
        "n": int(model.nobs),
    }


def stable_quartiles(frame: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    n_quartile = int(math.ceil(len(frame) * 0.25))
    ranked = frame.sort_values("first_accuracy", ascending=False, kind="mergesort")
    return ranked.iloc[:n_quartile], ranked.iloc[-n_quartile:]


def dke_result(frame: pd.DataFrame, metric: str) -> Dict[str, object]:
    top, bottom = stable_quartiles(frame)
    x = pd.to_numeric(top["second_%s" % metric], errors="coerce").dropna().to_numpy(dtype=float)
    y = pd.to_numeric(bottom["second_%s" % metric], errors="coerce").dropna().to_numpy(dtype=float)
    result = stats.mannwhitneyu(x, y, alternative="greater")
    return {
        "n_top": int(len(x)),
        "n_bottom": int(len(y)),
        "top_mean": float(np.mean(x)),
        "bottom_mean": float(np.mean(y)),
        "mean_difference": float(np.mean(x) - np.mean(y)),
        "U": float(result.statistic),
        "p_value": float(result.pvalue),
        "cliffs_delta": cliffs_delta(x, y),
    }


def trust_result(frame: pd.DataFrame) -> Dict[str, object]:
    data = frame[["trust_second", "trust_first", "condition", "t_c", "x_c", "ati", "propensity", "order_id"]].dropna().copy()
    condition_model = smf.ols(
        "trust_second ~ trust_first + C(condition) + ati + propensity + C(order_id)", data=data
    ).fit()
    condition_test = joint_hc3_wald(condition_model, "C(condition)")
    order_test = joint_hc3_wald(condition_model, "C(order_id)")
    factorial_model = smf.ols(
        "trust_second ~ trust_first + t_c * x_c + ati + propensity + C(order_id)", data=data
    ).fit()
    return {
        "n": int(len(data)),
        "condition": condition_test,
        "order": order_test,
        "Tutorial": robust_parameter(factorial_model, "t_c"),
        "XAI": robust_parameter(factorial_model, "x_c"),
        "Tutorial:XAI": robust_parameter(factorial_model, "t_c:x_c"),
    }


def append_loo(rows: List[Dict[str, object]], analysis: str, outcome: str, effect: str,
               omitted: str, result: Mapping[str, object], full_p: float) -> None:
    p_value = result.get("p_value")
    rows.append({
        "analysis": analysis,
        "outcome": outcome,
        "effect_or_group": effect,
        "omitted_order": omitted,
        "n": result.get("n", result.get("n_top")),
        "statistic": result.get("statistic", result.get("F", result.get("U"))),
        "p_value": p_value,
        "significant_0_0125": bool(p_value is not None and float(p_value) < ALPHA_PUBLISHED),
        "full_sample_p": full_p,
        "decision_flip_vs_full": bool(
            p_value is not None and (float(p_value) < ALPHA_PUBLISHED) != (float(full_p) < ALPHA_PUBLISHED)
        ),
    })


def leave_one_order_out(frame: pd.DataFrame) -> Tuple[List[Dict[str, object]], List[Dict[str, object]]]:
    rows: List[Dict[str, object]] = []
    summaries: List[Dict[str, object]] = []
    order_ids = sorted(frame["order_id"].astype(int).unique())

    tests: List[Tuple[str, str, str, object]] = []
    # H1 held-out omnibus tests.
    for label, metric in METRICS:
        def compute_h1(data, metric=metric):
            value = "second_%s" % metric
            model = smf.ols("Q('%s') ~ C(group_first) + C(order_id)" % value, data=data.dropna(subset=[value])).fit()
            test = joint_hc3_wald(model, "C(group_first)")
            return {"n": int(model.nobs), "F": test["F"], "p_value": test["p_value"]}
        tests.append(("H1 held-out", label, "Calibration group", compute_h1))

    for group in ("all", "under", "over"):
        tests.append(("H2 calibration", "Absolute miscalibration", group, lambda data, group=group: h2_result(data, group)))

    for group in ("under", "over"):
        for label, metric in METRICS:
            tests.append(("H3 paired change", label, group, lambda data, group=group, metric=metric: h3_result(data, group, metric)))

    for label, metric in METRICS:
        for effect in ("Tutorial", "XAI", "Tutorial:XAI"):
            def compute_h4(data, metric=metric, effect=effect):
                result = h4_result(data, metric)[effect]
                return {"n": int(data["second_%s" % metric].notna().sum()), "statistic": result["statistic"], "p_value": result["p_value"]}
            tests.append(("H4 order-adjusted", label, effect, compute_h4))

    for label, metric in METRICS[1:]:
        tests.append(("DKE held-out", label, "Top > bottom", lambda data, metric=metric: dke_result(data, metric)))

    def trust_condition(data):
        result = trust_result(data)["condition"]
        return {"n": int(len(data)), "F": result["F"], "p_value": result["p_value"]}
    tests.append(("Trust baseline-adjusted", "Second-wave trust", "Four-condition omnibus", trust_condition))
    for effect in ("Tutorial", "XAI", "Tutorial:XAI"):
        def trust_factor(data, effect=effect):
            result = trust_result(data)[effect]
            return {"n": int(len(data)), "statistic": result["statistic"], "p_value": result["p_value"]}
        tests.append(("Trust baseline-adjusted", "Second-wave trust", effect, trust_factor))

    for analysis, outcome, effect, function in tests:
        full = function(frame)
        full_p = float(full["p_value"])
        append_loo(rows, analysis, outcome, effect, "none", full, full_p)
        pvalues = []
        flips = 0
        for order_id in order_ids:
            subset = frame.loc[frame["order_id"].astype(int) != int(order_id)].copy()
            result = function(subset)
            append_loo(rows, analysis, outcome, effect, str(order_id), result, full_p)
            if result.get("p_value") is not None:
                pvalues.append(float(result["p_value"]))
                flips += int((float(result["p_value"]) < ALPHA_PUBLISHED) != (full_p < ALPHA_PUBLISHED))
        summaries.append({
            "analysis": analysis,
            "outcome": outcome,
            "effect_or_group": effect,
            "full_p": full_p,
            "full_significant_0_0125": bool(full_p < ALPHA_PUBLISHED),
            "loo_p_min": float(min(pvalues)) if pvalues else None,
            "loo_p_median": float(np.median(pvalues)) if pvalues else None,
            "loo_p_max": float(max(pvalues)) if pvalues else None,
            "loo_decision_flips_n": int(flips),
            "loo_orders_n": int(len(pvalues)),
            "proportion_same_decision": float(1.0 - flips / float(len(pvalues))) if pvalues else None,
        })
    return rows, summaries


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    frame = prepare_frame(build_clean_metric_frame(repo, undefined_ratio="zero"))
    distribution = order_distribution(frame)
    fixed = h1_fixed_effects(frame)
    for label, metric in METRICS:
        h4 = h4_result(frame, metric)
        for effect in ("Tutorial", "XAI", "Tutorial:XAI"):
            fixed.append({
                "analysis": "H4 order-adjusted factorial",
                "metric": label,
                "n": h4["n"],
                "effect": effect,
                "estimate": h4[effect]["estimate"],
                "hc3_se": h4[effect]["se"],
                "hc3_p": h4[effect]["p_value"],
                "significant_0_0125": bool(h4[effect]["p_value"] < ALPHA_PUBLISHED),
                "order_F_HC3": h4["Order"]["F"],
                "order_p_HC3": h4["Order"]["p_value"],
            })
    trust = trust_result(frame)
    fixed.append({
        "analysis": "Trust baseline-adjusted condition",
        "metric": "Second-wave trust",
        "n": trust["n"],
        "effect": "Four-condition omnibus",
        "hc3_F": trust["condition"]["F"],
        "hc3_p": trust["condition"]["p_value"],
        "significant_0_0125": bool(trust["condition"]["p_value"] < ALPHA_PUBLISHED),
        "order_F_HC3": trust["order"]["F"],
        "order_p_HC3": trust["order"]["p_value"],
    })

    loo_rows, loo_summary = leave_one_order_out(frame)
    sensitive = [row for row in loo_summary if int(row["loo_decision_flips_n"]) > 0]
    significant_order_effects = [
        row for row in fixed
        if row.get("order_p_HC3") is not None and float(row["order_p_HC3"]) < ALPHA_PUBLISHED
    ]
    memo = {
        "rb_id": "RB-18",
        "concern": "Task-order heterogeneity",
        "classification": "Specification-sensitive" if sensitive else "Stable",
        "leave_one_order_out_decision_sensitive_tests_n": int(len(sensitive)),
        "leave_one_order_out_decision_sensitive_tests": sensitive,
        "significant_order_fixed_effects_n": int(len(significant_order_effects)),
        "significant_order_fixed_effects": significant_order_effects,
        "interpretation": (
            "Order fixed effects and leave-one-order-out analyses separate treatment or calibration conclusions from "
            "heterogeneity induced by the ten constrained task sequences. A decision flip under omission of one order "
            "is treated as specification sensitivity, not as a computational reproduction failure."
        ),
    }
    summary = {
        "schema_version": "1.0",
        "stage": "RB-18 task-order heterogeneity",
        "sample_n": int(len(frame)),
        "order_levels_n": int(frame["order_id"].nunique()),
        "passed": True,
        "upstream_util_imported": False,
        "participant_level_data_emitted": False,
        "classification": memo["classification"],
        "memo": memo,
    }

    write_tsv(out / "rb18_order_distribution.tsv", distribution)
    write_tsv(out / "rb18_order_fixed_effects.tsv", fixed)
    write_tsv(out / "rb18_leave_one_order_out.tsv", loo_rows)
    write_tsv(out / "rb18_leave_one_order_out_summary.tsv", loo_summary)
    write_json(out / "rb18_memo.json", memo)
    write_json(out / "rb18_summary.json", summary)
    (out / "RB18_STATUS.md").write_text(
        "# RB-18 Task-Order Heterogeneity\n\n"
        "- Execution: **PASS**\n"
        "- Classification: **%s**\n"
        "- Leave-one-order-out tests with decision flips: **%d**\n"
        "- Significant order fixed effects at .0125: **%d**\n"
        "- Upstream `util.py` imported: **NO**\n"
        "- Participant-level data emitted: **NO**\n" % (
            memo["classification"], len(sensitive), len(significant_order_effects)
        ),
        encoding="utf-8",
    )
    print(json.dumps({"passed": True, "classification": memo["classification"], "sensitive_tests": len(sensitive)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
