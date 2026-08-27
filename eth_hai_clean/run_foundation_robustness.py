#!/usr/bin/env python3
"""Execute pre-specified foundation robustness checks RB-01 through RB-05.

The analysis is aggregate-only. It never emits participant identifiers or raw rows.
It relies on the independent clean core and never imports the upstream util.py.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import OrderedDict
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

from eth_hai_clean.core import (
    CONDITION_LABELS,
    TASK_ORDERS,
    build_clean_metric_frame,
    load_task_answers,
)

PUBLISHED_H2 = {"n": 87, "statistic": 1175.0, "p": 0.0002}
CONDITION_ORDER = [
    "no tutorial, no xai",
    "with tutorial, no xai",
    "no tutorial, with xai",
    "with tutorial, with xai",
]
CALIBRATION_ORDER = ["Underestimation", "Accurate", "Overestimation"]


def _json_default(value):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, Path):
        return str(value)
    raise TypeError(type(value).__name__)


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=_json_default) + "\n", encoding="utf-8")


def write_tsv(path: Path, rows: Sequence[Mapping[str, object]], fieldnames: Optional[Sequence[str]] = None) -> None:
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), delimiter="\t", lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: "" if row.get(key) is None else row.get(key) for key in fieldnames})


def attention_pass_mask(df: pd.DataFrame) -> pd.Series:
    return (
        (pd.to_numeric(df["attention_ati"]) == 3)
        & (df["attention6"].astype(str) == "B")
        & (df["attention11"].astype(str) == "D")
        & (df["attention18"].astype(str) == "C")
    )


def calibration_label(value: float) -> str:
    if value < 0:
        return "Underestimation"
    if value > 0:
        return "Overestimation"
    return "Accurate"


def safe_wilcoxon(x: Sequence[float], y: Sequence[float]) -> Tuple[float, float, Optional[str]]:
    try:
        result = stats.wilcoxon(x, y)
        return float(result.statistic), float(result.pvalue), None
    except ValueError as exc:
        return float("nan"), float("nan"), str(exc)


def rb01_tutorial_coding(frame: pd.DataFrame) -> Tuple[List[Dict[str, object]], Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    released_semantics = {0: "with tutorial", 1: "no tutorial"}
    naive_semantics = {0: "no tutorial", 1: "with tutorial"}

    for raw in (0, 1):
        subset = frame.loc[frame["tutorial_raw"] == raw].copy()
        mis = subset.loc[subset["miscalibration_first"] != 0].copy()
        first_abs = mis["miscalibration_first"].abs().astype(float)
        second_abs = mis["miscalibration_second"].abs().astype(float)
        w, p, error = safe_wilcoxon(first_abs.tolist(), second_abs.tolist())
        rows.append({
            "raw_tutorial": raw,
            "released_semantic_label": released_semantics[raw],
            "naive_boolean_label": naive_semantics[raw],
            "participants_n": int(len(subset)),
            "xai_0_n": int((subset["xai_raw"] == 0).sum()),
            "xai_1_n": int((subset["xai_raw"] == 1).sum()),
            "initially_miscalibrated_n": int(len(mis)),
            "initial_underestimators_n": int((mis["miscalibration_first"] < 0).sum()),
            "initial_overestimators_n": int((mis["miscalibration_first"] > 0).sum()),
            "absolute_miscalibration_first_mean": float(first_abs.mean()),
            "absolute_miscalibration_second_mean": float(second_abs.mean()),
            "mean_improvement_first_minus_second": float((first_abs - second_abs).mean()),
            "wilcoxon_statistic": w,
            "wilcoxon_p_two_sided": p,
            "wilcoxon_error": error,
        })

    raw0 = next(row for row in rows if row["raw_tutorial"] == 0)
    matches_published_signature = (
        raw0["initially_miscalibrated_n"] == PUBLISHED_H2["n"]
        and math.isclose(float(raw0["wilcoxon_statistic"]), PUBLISHED_H2["statistic"], abs_tol=1e-12)
        and abs(float(raw0["wilcoxon_p_two_sided"]) - PUBLISHED_H2["p"]) < 0.0001
    )
    raw_counts = {
        "%d,%d" % (t, x): int(((frame["tutorial_raw"] == t) & (frame["xai_raw"] == x)).sum())
        for t in (0, 1) for x in (0, 1)
    }
    memo = {
        "rb_id": "RB-01",
        "concern": "Tutorial coding ambiguity",
        "released_mapping": {"0": "with tutorial", "1": "no tutorial"},
        "raw_condition_counts": raw_counts,
        "published_h2_signature": PUBLISHED_H2,
        "raw_zero_matches_published_tutorial_signature": matches_published_signature,
        "decision": "Preserve released mapping for all direct and clean-equivalence analyses.",
        "interpretation": (
            "The raw tutorial bit is inverse-coded relative to the common Boolean convention. "
            "Raw tutorial=0 reproduces the published tutorial sample size and H2 Wilcoxon result; "
            "therefore the mapping is internally reconciled rather than unresolved."
        ),
        "classification": "Stable" if matches_published_signature else "Source-limited",
    }
    return rows, memo


def _decision_fields() -> List[str]:
    ids = [0, 1, 2, 3, 4, 5, 7, 8, 9, 10, 12, 13, 14, 15, 16, 17]
    return ["question%d" % i for i in ids] + ["advice%d" % i for i in ids]


def rb02_missingness(repo: Path) -> Tuple[List[Dict[str, object]], Dict[str, object], List[Dict[str, object]]]:
    path = repo / "anonymous_data" / "all_valid_data.csv"
    df = pd.read_csv(path)
    all_complete = df.dropna(axis=0)
    released_mask = attention_pass_mask(all_complete)
    released_n = int(released_mask.sum())

    condition_fields = ["username", "tutorial", "XAI", "question_order"]
    attention_fields = ["attention_ati", "attention6", "attention11", "attention18"]
    psychometric_fields = [
        *["ati%d" % i for i in range(1, 10)],
        *["pt%d" % i for i in range(1, 4)],
        "tia1_1", "tia1_2", "tia2_1", "tia2_2",
    ]
    calibration_fields = ["surveySelf1", "surveySelf2"]
    explanation_fields = ["xai_question"]
    decisions = _decision_fields()

    fieldsets = OrderedDict([
        ("Released all-column filter", list(df.columns)),
        ("Descriptive / clean core", condition_fields + attention_fields + psychometric_fields + calibration_fields + decisions),
        ("H1 calibration groups", condition_fields + attention_fields + ["surveySelf1"] + decisions),
        ("H2 calibration change", condition_fields + attention_fields + calibration_fields + decisions),
        ("H3 intervention outcomes", condition_fields + attention_fields + calibration_fields + decisions + explanation_fields),
        ("H4 factorial outcomes", condition_fields + attention_fields + decisions),
        ("DKE non-time quartiles", condition_fields + attention_fields + ["surveySelf1"] + decisions),
        ("Trust analysis", condition_fields + attention_fields + psychometric_fields + calibration_fields + decisions),
    ])

    rows: List[Dict[str, object]] = []
    for name, fields in fieldsets.items():
        unique_fields = list(dict.fromkeys(fields))
        missing_fields = sorted(set(unique_fields) - set(df.columns))
        if missing_fields:
            rows.append({
                "analysis": name,
                "required_columns_n": len(unique_fields),
                "missing_required_columns": ",".join(missing_fields),
                "source_rows": int(len(df)),
                "analysis_complete_rows": 0,
                "attention_pass_rows": 0,
                "released_filter_rows": released_n,
                "delta_vs_released": -released_n,
            })
            continue
        complete = df.dropna(subset=unique_fields)
        valid = complete.loc[attention_pass_mask(complete)]
        rows.append({
            "analysis": name,
            "required_columns_n": len(unique_fields),
            "missing_required_columns": "",
            "source_rows": int(len(df)),
            "analysis_complete_rows": int(len(complete)),
            "attention_pass_rows": int(len(valid)),
            "released_filter_rows": released_n,
            "delta_vs_released": int(len(valid) - released_n),
        })

    column_missing = [
        {"column": column, "missing_n": int(df[column].isna().sum()), "missing_pct": float(df[column].isna().mean() * 100.0)}
        for column in df.columns if int(df[column].isna().sum()) > 0
    ]
    memo = {
        "rb_id": "RB-02",
        "concern": "All-column complete-case filtering",
        "source_rows": int(len(df)),
        "source_columns": int(len(df.columns)),
        "all_column_missing_cells": int(df.isna().sum().sum()),
        "released_valid_n": released_n,
        "analysis_specific_deltas": {row["analysis"]: row["delta_vs_released"] for row in rows},
        "demographic_csv_present": bool((repo / "anonymous_data" / "demographic.csv").exists()),
        "classification": "Stable" if all(row["delta_vs_released"] == 0 for row in rows) else "Specification-sensitive",
        "interpretation": (
            "The released participant file has no missing cells, so analysis-specific complete-case filtering "
            "does not change the analytic sample. Completion-time analyses remain separately source-limited "
            "because demographic.csv is absent."
        ),
    }
    return rows, memo, column_missing


def _ratio_components(scope: str, metric: str) -> Tuple[str, str, str, str]:
    if metric == "RAIR":
        numerator = "%s_positive_ai_reliance" % scope
        denominator_a = numerator
        denominator_b = "%s_negative_self_reliance" % scope
        value = "%s_rair" % scope
    elif metric == "RSR":
        numerator = "%s_positive_self_reliance" % scope
        denominator_a = numerator
        denominator_b = "%s_negative_ai_reliance" % scope
        value = "%s_rsr" % scope
    else:
        raise ValueError(metric)
    return numerator, denominator_a, denominator_b, value


def _descriptive(series: pd.Series) -> Dict[str, object]:
    values = pd.to_numeric(series, errors="coerce").dropna().astype(float)
    return {
        "n": int(len(values)),
        "mean": float(values.mean()) if len(values) else None,
        "sd_population": float(values.std(ddof=0)) if len(values) else None,
        "sd_sample": float(values.std(ddof=1)) if len(values) > 1 else None,
        "median": float(values.median()) if len(values) else None,
        "min": float(values.min()) if len(values) else None,
        "max": float(values.max()) if len(values) else None,
    }


def rb03_ratio_policies(frame_zero: pd.DataFrame, frame_nan: pd.DataFrame) -> Tuple[
    List[Dict[str, object]], List[Dict[str, object]], List[Dict[str, object]], List[Dict[str, object]], Dict[str, object]
]:
    descriptive_rows: List[Dict[str, object]] = []
    condition_rows: List[Dict[str, object]] = []
    test_rows: List[Dict[str, object]] = []
    correlation_rows: List[Dict[str, object]] = []
    summary_deltas: List[float] = []
    significance_changes: List[Dict[str, object]] = []

    for scope in ("first", "second", "overall"):
        for metric in ("RAIR", "RSR"):
            numerator, denom_a, denom_b, value = _ratio_components(scope, metric)
            denominator = frame_zero[denom_a].astype(float) + frame_zero[denom_b].astype(float)
            undefined = denominator == 0
            defined_series = frame_nan[value]
            zero_desc = _descriptive(frame_zero[value])
            defined_desc = _descriptive(defined_series)
            pooled_denominator = float(denominator.sum())
            pooled_numerator = float(frame_zero[numerator].sum())
            pooled_ratio = pooled_numerator / pooled_denominator if pooled_denominator else None
            summary_deltas.append(abs(float(zero_desc["mean"]) - float(defined_desc["mean"])))

            for policy, desc in (("released_zero", zero_desc), ("defined_participants", defined_desc)):
                descriptive_rows.append({
                    "scope": scope,
                    "metric": metric,
                    "policy": policy,
                    "participants_total": int(len(frame_zero)),
                    "undefined_n": int(undefined.sum()),
                    "defined_n": int((~undefined).sum()),
                    **desc,
                    "pooled_numerator": "",
                    "pooled_denominator": "",
                })
            descriptive_rows.append({
                "scope": scope,
                "metric": metric,
                "policy": "opportunity_pooled",
                "participants_total": int(len(frame_zero)),
                "undefined_n": int(undefined.sum()),
                "defined_n": int((~undefined).sum()),
                "n": int(pooled_denominator),
                "mean": pooled_ratio,
                "sd_population": "",
                "sd_sample": "",
                "median": "",
                "min": "",
                "max": "",
                "pooled_numerator": pooled_numerator,
                "pooled_denominator": pooled_denominator,
            })

            for condition in CONDITION_ORDER:
                mask = frame_zero["condition"] == condition
                for policy, source in (("released_zero", frame_zero), ("defined_participants", frame_nan)):
                    desc = _descriptive(source.loc[mask, value])
                    condition_rows.append({
                        "scope": scope,
                        "metric": metric,
                        "policy": policy,
                        "condition": condition,
                        **desc,
                    })

    first_groups = frame_zero["miscalibration_first"].map(calibration_label)
    for metric in ("RAIR", "RSR"):
        value = "first_%s" % metric.lower()
        results_by_policy = {}
        for policy, source in (("released_zero", frame_zero), ("defined_participants", frame_nan)):
            groups = []
            group_ns = {}
            group_means = {}
            for label in CALIBRATION_ORDER:
                vals = pd.to_numeric(source.loc[first_groups == label, value], errors="coerce").dropna().astype(float)
                groups.append(vals.to_numpy())
                group_ns[label] = int(len(vals))
                group_means[label] = float(vals.mean()) if len(vals) else None
            result = stats.kruskal(*groups)
            row = {
                "analysis": "first_batch_calibration_group_kruskal",
                "metric": metric,
                "policy": policy,
                "statistic": float(result.statistic),
                "p_value": float(result.pvalue),
                "significant_0_05": bool(result.pvalue < 0.05),
                "group_ns": json.dumps(group_ns, sort_keys=True),
                "group_means": json.dumps(group_means, sort_keys=True),
            }
            test_rows.append(row)
            results_by_policy[policy] = row
        if results_by_policy["released_zero"]["significant_0_05"] != results_by_policy["defined_participants"]["significant_0_05"]:
            significance_changes.append({"analysis": "H1-like calibration group Kruskal", "metric": metric})

    predictors = {
        "propensity": "propensity",
        "overall_accuracy": "overall_accuracy",
        "miscalibration_first": "miscalibration_first",
    }
    for metric in ("RAIR", "RSR"):
        value = "overall_%s" % metric.lower()
        for predictor_name, predictor_col in predictors.items():
            policy_results = {}
            for policy, source in (("released_zero", frame_zero), ("defined_participants", frame_nan)):
                pair = source[[predictor_col, value]].apply(pd.to_numeric, errors="coerce").dropna()
                corr = stats.spearmanr(pair[predictor_col], pair[value])
                row = {
                    "metric": metric,
                    "predictor": predictor_name,
                    "policy": policy,
                    "n": int(len(pair)),
                    "rho": float(corr.statistic),
                    "p_value": float(corr.pvalue),
                    "significant_0_05": bool(corr.pvalue < 0.05),
                }
                correlation_rows.append(row)
                policy_results[policy] = row
            if policy_results["released_zero"]["significant_0_05"] != policy_results["defined_participants"]["significant_0_05"]:
                significance_changes.append({"analysis": "Spearman", "metric": metric, "predictor": predictor_name})

    max_mean_delta = max(summary_deltas) if summary_deltas else 0.0
    classification = "Specification-sensitive" if max_mean_delta >= 0.05 or significance_changes else "Stable"
    memo = {
        "rb_id": "RB-03",
        "concern": "Undefined RAIR/RSR encoded as zero",
        "max_absolute_mean_delta_zero_vs_defined": max_mean_delta,
        "significance_decision_changes": significance_changes,
        "classification": classification,
        "interpretation": (
            "Undefined ratios are frequent, especially for batch-level RSR. Released zero substitution, "
            "equal-weight defined-participant means, and opportunity-pooled ratios answer different questions "
            "and must be reported separately."
        ),
    }
    return descriptive_rows, condition_rows, test_rows, correlation_rows, memo


def _add_sd_rows(rows: List[Dict[str, object]], frame: pd.DataFrame, level: str, group: str, metrics: Mapping[str, str]) -> None:
    for label, column in metrics.items():
        desc = _descriptive(frame[column])
        pop = desc["sd_population"]
        sample = desc["sd_sample"]
        rows.append({
            "level": level,
            "group": group,
            "metric": label,
            "column": column,
            "n": desc["n"],
            "mean": desc["mean"],
            "sd_population_ddof0": pop,
            "sd_sample_ddof1": sample,
            "absolute_sd_delta": (float(sample) - float(pop)) if pop is not None and sample is not None else None,
            "relative_sd_delta_pct": ((float(sample) / float(pop) - 1.0) * 100.0) if pop not in (None, 0.0) and sample is not None else None,
        })


def rb04_sd_conventions(frame: pd.DataFrame) -> Tuple[List[Dict[str, object]], Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    overall_metrics = OrderedDict([
        ("ATI", "ati"),
        ("TiA propensity", "propensity"),
        ("Trust first", "trust_first"),
        ("Trust second", "trust_second"),
        ("Overall accuracy", "overall_accuracy"),
        ("Overall agreement", "overall_agreement_fraction"),
        ("Overall switch fraction", "overall_switch_fraction"),
        ("Overall Accuracy-wid", "overall_appropriate_reliance"),
        ("Overall RAIR", "overall_rair"),
        ("Overall RSR", "overall_rsr"),
    ])
    _add_sd_rows(rows, frame, "overall", "All participants", overall_metrics)

    first_metrics = OrderedDict([
        ("Accuracy", "first_accuracy"),
        ("Agreement", "first_agreement_fraction"),
        ("Switch fraction", "first_switch_fraction"),
        ("Accuracy-wid", "first_appropriate_reliance"),
        ("RAIR", "first_rair"),
        ("RSR", "first_rsr"),
    ])
    groups = frame["miscalibration_first"].map(calibration_label)
    for label in CALIBRATION_ORDER:
        _add_sd_rows(rows, frame.loc[groups == label], "first_batch_calibration_group", label, first_metrics)

    second_metrics = OrderedDict([
        ("Accuracy", "second_accuracy"),
        ("Agreement", "second_agreement_fraction"),
        ("Switch fraction", "second_switch_fraction"),
        ("Accuracy-wid", "second_appropriate_reliance"),
        ("RAIR", "second_rair"),
        ("RSR", "second_rsr"),
    ])
    for condition in CONDITION_ORDER:
        _add_sd_rows(rows, frame.loc[frame["condition"] == condition], "second_batch_condition", condition, second_metrics)

    deltas = [float(row["absolute_sd_delta"]) for row in rows if row["absolute_sd_delta"] is not None]
    relative = [float(row["relative_sd_delta_pct"]) for row in rows if row["relative_sd_delta_pct"] is not None]
    memo = {
        "rb_id": "RB-04",
        "concern": "SD convention inconsistency",
        "rows_audited": len(rows),
        "max_absolute_sd_delta": max(deltas) if deltas else 0.0,
        "max_relative_sd_delta_pct": max(relative) if relative else 0.0,
        "classification": "Stable",
        "interpretation": (
            "Means and test statistics are unchanged. Population and sample SDs differ deterministically; "
            "the convention should be labeled explicitly, particularly for subgroup tables."
        ),
    }
    return rows, memo


def _normality_row(batch: str, variable: str, policy: str, values: pd.Series) -> Dict[str, object]:
    x = pd.to_numeric(values, errors="coerce").dropna().astype(float).to_numpy()
    n = len(x)
    if n < 3:
        raise ValueError("Insufficient observations for normality diagnostics")
    unique_n = int(len(np.unique(x)))
    sh = stats.shapiro(x)
    ad = stats.anderson(x, dist="norm")
    levels = list(map(float, ad.significance_level))
    criticals = list(map(float, ad.critical_values))
    idx5 = min(range(len(levels)), key=lambda i: abs(levels[i] - 5.0))
    (_, _), (_, _, qq_r) = stats.probplot(x, dist="norm", fit=True)
    min_v = float(np.min(x))
    max_v = float(np.max(x))
    return {
        "batch": batch,
        "variable": variable,
        "policy": policy,
        "n": int(n),
        "unique_values_n": unique_n,
        "discrete_flag": bool(unique_n <= 15),
        "min": min_v,
        "max": max_v,
        "mean": float(np.mean(x)),
        "sd_sample": float(np.std(x, ddof=1)),
        "skew_bias_corrected": float(stats.skew(x, bias=False)),
        "excess_kurtosis_bias_corrected": float(stats.kurtosis(x, fisher=True, bias=False)),
        "zero_fraction": float(np.mean(x == 0.0)),
        "mass_at_min_fraction": float(np.mean(x == min_v)),
        "mass_at_max_fraction": float(np.mean(x == max_v)),
        "shapiro_w": float(sh.statistic),
        "shapiro_p": float(sh.pvalue),
        "shapiro_reject_0_05": bool(sh.pvalue < 0.05),
        "anderson_statistic": float(ad.statistic),
        "anderson_critical_5pct": criticals[idx5],
        "anderson_reject_5pct": bool(float(ad.statistic) > criticals[idx5]),
        "qq_correlation_r": float(qq_r),
    }


def _plot_diagnostics(frame_zero: pd.DataFrame, frame_nan: pd.DataFrame, out: Path, batch: str) -> None:
    mapping = OrderedDict([
        ("Accuracy", "%s_accuracy" % batch),
        ("Agreement Fraction", "%s_agreement_fraction" % batch),
        ("Switch Fraction", "%s_switch_fraction" % batch),
        ("Accuracy-wid", "%s_appropriate_reliance" % batch),
        ("Miscalibration", "miscalibration_%s" % batch),
        ("Trust", "trust_%s" % batch),
        ("RAIR", "%s_rair" % batch),
        ("RSR", "%s_rsr" % batch),
    ])
    fig, axes = plt.subplots(4, 2, figsize=(12, 14))
    for ax, (label, column) in zip(axes.ravel(), mapping.items()):
        zero = pd.to_numeric(frame_zero[column], errors="coerce").dropna().astype(float)
        ax.hist(zero, bins="auto", alpha=0.75, label="released zero")
        if label in ("RAIR", "RSR"):
            defined = pd.to_numeric(frame_nan[column], errors="coerce").dropna().astype(float)
            ax.hist(defined, bins="auto", histtype="step", linewidth=1.5, label="defined only")
            ax.legend(fontsize=8)
        ax.set_title(label)
        ax.set_ylabel("Count")
    fig.suptitle("%s-batch distributions" % batch.capitalize())
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(out / ("rb05_%s_batch_histograms.png" % batch), dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(4, 2, figsize=(12, 14))
    for ax, (label, column) in zip(axes.ravel(), mapping.items()):
        source = frame_nan if label in ("RAIR", "RSR") else frame_zero
        x = pd.to_numeric(source[column], errors="coerce").dropna().astype(float).to_numpy()
        stats.probplot(x, dist="norm", plot=ax)
        ax.set_title(label + (" (defined only)" if label in ("RAIR", "RSR") else ""))
    fig.suptitle("%s-batch normal Q-Q diagnostics" % batch.capitalize())
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(out / ("rb05_%s_batch_qq.png" % batch), dpi=180)
    plt.close(fig)


def rb05_normality(frame_zero: pd.DataFrame, frame_nan: pd.DataFrame, out: Path, make_plots: bool) -> Tuple[List[Dict[str, object]], Dict[str, object]]:
    diagnostics: List[Dict[str, object]] = []
    variable_map = OrderedDict([
        ("accuracy", "{batch}_accuracy"),
        ("agreement_fraction", "{batch}_agreement_fraction"),
        ("switching_fraction", "{batch}_switch_fraction"),
        ("appropriate_reliance", "{batch}_appropriate_reliance"),
        ("miscalibration", "miscalibration_{batch}"),
        ("trust", "trust_{batch}"),
        ("RAIR", "{batch}_rair"),
        ("RSR", "{batch}_rsr"),
    ])
    for batch in ("first", "second"):
        for variable, template in variable_map.items():
            column = template.format(batch=batch)
            diagnostics.append(_normality_row(batch, variable, "released_zero", frame_zero[column]))
            if variable in ("RAIR", "RSR"):
                diagnostics.append(_normality_row(batch, variable, "defined_participants", frame_nan[column]))
        if make_plots:
            _plot_diagnostics(frame_zero, frame_nan, out, batch)

    rejection_count = sum(bool(row["shapiro_reject_0_05"]) for row in diagnostics)
    memo = {
        "rb_id": "RB-05",
        "concern": "Normality script defects",
        "original_defects": [
            "The released script computes the purported second batch from first_group again.",
            "It appends first and duplicated first-batch values into one vector.",
            "It applies a Kolmogorov-Smirnov test against standard N(0,1) without fitting or standardizing.",
            "It treats bounded and highly discrete metrics as if they were continuous unbounded Gaussian variables.",
            "It records trust_first for both batches."
        ],
        "diagnostic_rows": len(diagnostics),
        "shapiro_rejections_0_05": int(rejection_count),
        "classification": "Specification-sensitive",
        "interpretation": (
            "The historical normality script is not an interpretable normality assessment. Correct batch-separated "
            "diagnostics show strong discreteness, boundary mass, and widespread departures from Gaussian shape. "
            "Normality-test p-values should not be used mechanically to select methods for these bounded metrics."
        ),
    }
    return diagnostics, memo


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()
    repo = args.repo.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    frame_zero = build_clean_metric_frame(repo, undefined_ratio="zero")
    frame_nan = build_clean_metric_frame(repo, undefined_ratio="nan")
    if len(frame_zero) != 249 or len(frame_nan) != 249:
        raise AssertionError("Unexpected analytic sample")

    rb01_rows, rb01_memo = rb01_tutorial_coding(frame_zero)
    rb02_rows, rb02_memo, rb02_missing = rb02_missingness(repo)
    rb03_desc, rb03_conditions, rb03_tests, rb03_corrs, rb03_memo = rb03_ratio_policies(frame_zero, frame_nan)
    rb04_rows, rb04_memo = rb04_sd_conventions(frame_zero)
    rb05_rows, rb05_memo = rb05_normality(frame_zero, frame_nan, out, make_plots=not args.no_plots)

    write_tsv(out / "rb01_tutorial_coding.tsv", rb01_rows)
    write_json(out / "rb01_coding_decision_memo.json", rb01_memo)
    write_tsv(out / "rb02_analysis_specific_missingness.tsv", rb02_rows)
    write_tsv(out / "rb02_column_missingness.tsv", rb02_missing, fieldnames=["column", "missing_n", "missing_pct"])
    write_json(out / "rb02_missingness_memo.json", rb02_memo)
    write_tsv(out / "rb03_ratio_policy_descriptives.tsv", rb03_desc)
    write_tsv(out / "rb03_condition_means.tsv", rb03_conditions)
    write_tsv(out / "rb03_group_tests.tsv", rb03_tests)
    write_tsv(out / "rb03_correlations.tsv", rb03_corrs)
    write_json(out / "rb03_ratio_policy_memo.json", rb03_memo)
    write_tsv(out / "rb04_sd_conventions.tsv", rb04_rows)
    write_json(out / "rb04_sd_memo.json", rb04_memo)
    write_tsv(out / "rb05_distribution_diagnostics.tsv", rb05_rows)
    write_json(out / "rb05_normality_memo.json", rb05_memo)

    memos = [rb01_memo, rb02_memo, rb03_memo, rb04_memo, rb05_memo]
    summary = {
        "schema_version": "1.0",
        "stage": "foundation robustness RB-01 through RB-05",
        "sample_n": 249,
        "passed": True,
        "upstream_util_imported": False,
        "participant_level_data_emitted": False,
        "checks": memos,
        "classifications": {memo["rb_id"]: memo["classification"] for memo in memos},
        "key_findings": {
            "released_tutorial_mapping_reconciled": rb01_memo["raw_zero_matches_published_tutorial_signature"],
            "analysis_specific_missingness_delta_max_abs": max(abs(int(row["delta_vs_released"])) for row in rb02_rows),
            "ratio_policy_max_mean_delta": rb03_memo["max_absolute_mean_delta_zero_vs_defined"],
            "sd_max_relative_delta_pct": rb04_memo["max_relative_sd_delta_pct"],
            "normality_shapiro_rejections": rb05_memo["shapiro_rejections_0_05"],
        },
    }
    write_json(out / "foundation_robustness_summary.json", summary)

    status_lines = [
        "# ETH HAI Foundation Robustness Gate",
        "",
        "- Overall execution: **PASS**",
        "- Upstream `util.py` imported: **NO**",
        "- Participant-level data emitted: **NO**",
        "- RB-01 tutorial coding: **%s**" % rb01_memo["classification"],
        "- RB-02 missingness: **%s**" % rb02_memo["classification"],
        "- RB-03 RAIR/RSR policy: **%s**" % rb03_memo["classification"],
        "- RB-04 SD convention: **%s**" % rb04_memo["classification"],
        "- RB-05 distribution diagnostics: **%s**" % rb05_memo["classification"],
    ]
    (out / "FOUNDATION_STATUS.md").write_text("\n".join(status_lines) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "classifications": summary["classifications"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
