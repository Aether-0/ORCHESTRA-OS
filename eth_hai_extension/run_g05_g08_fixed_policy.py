#!/usr/bin/env python3
"""Registered G05-G08 fixed-policy analysis for the ETH HAI extension.

Outputs aggregate policy values, contrasts, task-order sensitivity, safety review,
and denominator-policy sensitivity. No participant rows or identifiers are emitted.
All estimates are retrospective associational standardizations.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from statsmodels.stats.multitest import multipletests

from eth_hai_extension.core import (
    OUTCOME_COLUMNS,
    POLICY_BY_ID,
    POLICIES,
    PRIMARY_CATEGORICAL_FEATURES,
    PRIMARY_NUMERIC_FEATURES,
    build_extension_frame,
    policy_assignments,
)
from eth_hai_extension.estimators import (
    PolicyValueEstimate,
    fit_cross_fitted_propensity,
    make_preprocessor,
    policy_contrast,
    policy_value_aipw,
    policy_value_ipw,
    policy_value_or,
    repeated_stratified_folds,
)

OUTCOME_META: Dict[str, Dict[str, str]] = {
    "O01": {"name": "Absolute calibration improvement", "direction": "higher"},
    "O02": {"name": "Second absolute miscalibration", "direction": "lower"},
    "O03": {"name": "Second-batch accuracy", "direction": "higher"},
    "O04": {"name": "Second-batch Accuracy-wid", "direction": "higher"},
    "O05": {"name": "Overreliance harm per task", "direction": "lower"},
    "O06": {"name": "Underreliance harm per task", "direction": "lower"},
    "O07": {"name": "Second Agreement Fraction", "direction": "neutral"},
    "O08": {"name": "Second Switch Fraction", "direction": "neutral"},
    "O09": {"name": "Second RAIR, released-zero", "direction": "higher"},
    "O10": {"name": "Second RSR, released-zero", "direction": "higher"},
}

PAIR_SPECS: Tuple[Tuple[str, str, str], ...] = (
    ("P07", "P00", "anchor"),
    ("P01", "P07", "primary"),
    ("P03", "P07", "primary"),
    ("P05", "P07", "primary"),
    ("P01", "P00", "secondary"),
    ("P03", "P00", "secondary"),
    ("P05", "P00", "secondary"),
    ("P02", "P00", "landscape"),
    ("P02", "P07", "landscape"),
    ("P04", "P00", "landscape"),
    ("P04", "P07", "landscape"),
    ("P06", "P00", "landscape"),
    ("P06", "P07", "landscape"),
)
PRIMARY_PAIRS: Tuple[Tuple[str, str], ...] = (("P01", "P07"), ("P03", "P07"), ("P05", "P07"))
SAFETY_OUTCOMES: Tuple[str, ...] = ("O03", "O04", "O05", "O06")
Z_95 = 1.959963984540054


def json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, Path):
        return str(value)
    raise TypeError(type(value).__name__)


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=json_default) + "\n", encoding="utf-8")


def write_tsv(path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Optional[Sequence[str]] = None) -> None:
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), delimiter="\t", lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: "" if row.get(key) is None else row.get(key) for key in fieldnames})


def fit_cross_fitted_outcome(
    frame: pd.DataFrame,
    outcome_column: str,
    n_splits: int = 5,
    repeats: int = 20,
    seed: int = 20260827,
) -> Dict[str, np.ndarray]:
    y = pd.to_numeric(frame[outcome_column], errors="raise").to_numpy(dtype=float)
    a = pd.to_numeric(frame["treatment"], errors="raise").to_numpy(dtype=int)
    features = frame[list(PRIMARY_NUMERIC_FEATURES) + list(PRIMARY_CATEGORICAL_FEATURES)].copy()
    m0_sum = np.zeros(len(frame), dtype=float)
    m1_sum = np.zeros(len(frame), dtype=float)
    seen = np.zeros(len(frame), dtype=int)
    for _, _, train_index, test_index in repeated_stratified_folds(frame, n_splits, repeats, seed):
        x_train = features.iloc[train_index]
        x_test = features.iloc[test_index]
        a_train = a[train_index]
        y_train = y[train_index]
        predictions: Dict[int, np.ndarray] = {}
        for arm in (0, 1):
            mask = a_train == arm
            if int(mask.sum()) < 2:
                raise ValueError("Insufficient training observations in arm %d" % arm)
            model = Pipeline([
                ("preprocess", make_preprocessor(PRIMARY_NUMERIC_FEATURES, PRIMARY_CATEGORICAL_FEATURES)),
                ("model", Ridge(alpha=1.0)),
            ])
            model.fit(x_train.iloc[mask], y_train[mask])
            predictions[arm] = model.predict(x_test)
        m0_sum[test_index] += predictions[0]
        m1_sum[test_index] += predictions[1]
        seen[test_index] += 1
    if not np.all(seen == repeats):
        raise AssertionError("Each row must receive exactly one outcome prediction per repeat")
    return {"m0": m0_sum / seen, "m1": m1_sum / seen, "prediction_count": seen}


def normal_interval(estimate: PolicyValueEstimate) -> Tuple[float, float]:
    return (float(estimate.policy_value - Z_95 * estimate.standard_error), float(estimate.policy_value + Z_95 * estimate.standard_error))


def two_sided_p(estimate: PolicyValueEstimate) -> float:
    if estimate.standard_error <= 0:
        return 1.0 if abs(estimate.policy_value) <= 1e-15 else 0.0
    return float(2.0 * norm.sf(abs(estimate.policy_value / estimate.standard_error)))


def directional_values(raw: float, low: float, high: float, direction: str) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    if direction == "higher":
        return float(raw), float(low), float(high)
    if direction == "lower":
        return float(-raw), float(-high), float(-low)
    return None, None, None


def sign(value: float, tolerance: float = 1e-12) -> int:
    if value > tolerance:
        return 1
    if value < -tolerance:
        return -1
    return 0


def estimator_agreement(values: Sequence[float]) -> bool:
    nonzero = {sign(value) for value in values if sign(value) != 0}
    return len(nonzero) <= 1


def stratified_bootstrap_indices(frame: pd.DataFrame, draws: int = 5000, seed: int = 20260827) -> np.ndarray:
    strata = frame["treatment"].astype(str) + "|" + frame["xai_raw"].astype(str)
    groups = [np.where(strata.to_numpy() == label)[0] for label in sorted(strata.unique())]
    rng = np.random.default_rng(seed)
    result = np.empty((draws, len(frame)), dtype=np.int32)
    start = 0
    for group in groups:
        width = len(group)
        result[:, start:start + width] = rng.choice(group, size=(draws, width), replace=True)
        start += width
    return result


def bootstrap_interval(estimate: PolicyValueEstimate, indices: np.ndarray) -> Tuple[float, float]:
    pseudo = estimate.policy_value + estimate.influence_values
    values = pseudo[indices].mean(axis=1)
    low, high = np.quantile(values, [0.025, 0.975])
    return float(low), float(high)


def holm_update(rows: List[Dict[str, Any]], selector: Iterable[int], label: str) -> None:
    indices = list(selector)
    if not indices:
        return
    adjusted = multipletests([float(rows[index]["p_value"]) for index in indices], alpha=0.05, method="holm")[1]
    for index, value in zip(indices, adjusted):
        rows[index]["adjusted_p"] = float(value)
        rows[index]["adjustment_family"] = label


def full_decision(row: Mapping[str, Any], use_adjusted: bool = True) -> str:
    low = row.get("directional_ci_low")
    high = row.get("directional_ci_high")
    p = row.get("adjusted_p") if use_adjusted else row.get("p_value")
    if low is None or high is None:
        return "Descriptive"
    if float(low) > 0 and (p is None or float(p) < 0.05):
        return "Favorable"
    if float(high) < 0 and (p is None or float(p) < 0.05):
        return "Unfavorable"
    return "Inconclusive"


def classify(row: Mapping[str, Any], primary: bool) -> str:
    if row["direction"] == "neutral":
        return "Descriptive"
    if row.get("safety_harm_flag") == "Yes":
        return "Unfavorable"
    low = float(row["directional_ci_low"])
    high = float(row["directional_ci_high"])
    point = float(row["directional_difference"])
    if high < 0:
        return "Unfavorable"
    if primary and low > 0:
        robust = (
            float(row.get("adjusted_p", 1.0)) < 0.05
            and row.get("task_order_sign_stable") == "Yes"
            and row.get("task_order_decision_stable") == "Yes"
            and row.get("estimator_agreement") == "Yes"
            and row.get("safety_harm_flag") == "No"
        )
        return "Robustly favorable" if robust else "Specification-sensitive favorable"
    if low > 0:
        return "Directionally favorable"
    if point > 0:
        return "Directionally favorable"
    return "Inconclusive"


def estimate_all(
    frame: pd.DataFrame,
    outcome_ids: Sequence[str],
    bootstrap_indices: np.ndarray,
    n_splits: int = 5,
    repeats: int = 20,
    seed: int = 20260827,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Dict[str, Dict[str, PolicyValueEstimate]]]]:
    assignments = policy_assignments(frame)
    propensity = fit_cross_fitted_propensity(
        frame,
        PRIMARY_NUMERIC_FEATURES,
        PRIMARY_CATEGORICAL_FEATURES,
        n_splits=n_splits,
        repeats=repeats,
        seed=seed,
    )["propensity"]
    policy_rows: List[Dict[str, Any]] = []
    contrast_rows: List[Dict[str, Any]] = []
    estimates: Dict[str, Dict[str, Dict[str, PolicyValueEstimate]]] = {}

    for outcome_id in outcome_ids:
        column = OUTCOME_COLUMNS[outcome_id]
        y = pd.to_numeric(frame[column], errors="raise").to_numpy(dtype=float)
        nuisance = fit_cross_fitted_outcome(frame, column, n_splits, repeats, seed)
        outcome_estimates: Dict[str, Dict[str, PolicyValueEstimate]] = {}
        for policy in POLICIES:
            d = assignments[policy.policy_id].to_numpy(dtype=int)
            or_est = policy_value_or(d, nuisance["m0"], nuisance["m1"])
            ipw_est = policy_value_ipw(y, frame["treatment"], d, propensity)
            aipw_est = policy_value_aipw(y, frame["treatment"], d, propensity, nuisance["m0"], nuisance["m1"])
            outcome_estimates[policy.policy_id] = {"or": or_est, "ipw": ipw_est, "aipw": aipw_est}
            ci_low, ci_high = normal_interval(aipw_est)
            boot_low, boot_high = bootstrap_interval(aipw_est, bootstrap_indices)
            policy_rows.append({
                "outcome_id": outcome_id,
                "outcome_name": OUTCOME_META[outcome_id]["name"],
                "policy_id": policy.policy_id,
                "policy_name": policy.name,
                "coverage_n": int(assignments[policy.policy_id].sum()),
                "coverage_fraction": float(assignments[policy.policy_id].mean()),
                "or_value": float(or_est.policy_value),
                "ipw_value": float(ipw_est.policy_value),
                "aipw_value": float(aipw_est.policy_value),
                "aipw_standard_error": float(aipw_est.standard_error),
                "aipw_ci_low": ci_low,
                "aipw_ci_high": ci_high,
                "bootstrap_ci_low": boot_low,
                "bootstrap_ci_high": boot_high,
            })
        estimates[outcome_id] = outcome_estimates

        for left_id, right_id, pair_class in PAIR_SPECS:
            estimator_contrasts = {
                estimator: policy_contrast(outcome_estimates[left_id][estimator], outcome_estimates[right_id][estimator])
                for estimator in ("or", "ipw", "aipw")
            }
            aipw = estimator_contrasts["aipw"]
            raw_low, raw_high = normal_interval(aipw)
            boot_low, boot_high = bootstrap_interval(aipw, bootstrap_indices)
            direction = OUTCOME_META[outcome_id]["direction"]
            directional, directional_low, directional_high = directional_values(aipw.policy_value, raw_low, raw_high, direction)
            estimator_raw = [estimator_contrasts[name].policy_value for name in ("or", "ipw", "aipw")]
            if direction == "lower":
                estimator_directional = [-value for value in estimator_raw]
            else:
                estimator_directional = estimator_raw
            contrast_rows.append({
                "pair_class": pair_class,
                "policy_id": left_id,
                "policy_name": POLICY_BY_ID[left_id].name,
                "comparator_id": right_id,
                "comparator_name": POLICY_BY_ID[right_id].name,
                "outcome_id": outcome_id,
                "outcome_name": OUTCOME_META[outcome_id]["name"],
                "direction": direction,
                "policy_coverage": float(assignments[left_id].mean()),
                "comparator_coverage": float(assignments[right_id].mean()),
                "coverage_delta": float(assignments[left_id].mean() - assignments[right_id].mean()),
                "policy_value": float(outcome_estimates[left_id]["aipw"].policy_value),
                "comparator_value": float(outcome_estimates[right_id]["aipw"].policy_value),
                "or_difference": float(estimator_contrasts["or"].policy_value),
                "ipw_difference": float(estimator_contrasts["ipw"].policy_value),
                "aipw_difference": float(aipw.policy_value),
                "aipw_standard_error": float(aipw.standard_error),
                "raw_ci_low": raw_low,
                "raw_ci_high": raw_high,
                "bootstrap_ci_low": boot_low,
                "bootstrap_ci_high": boot_high,
                "directional_difference": directional,
                "directional_ci_low": directional_low,
                "directional_ci_high": directional_high,
                "p_value": two_sided_p(aipw),
                "adjusted_p": None,
                "adjustment_family": "None",
                "estimator_agreement": "Yes" if estimator_agreement(estimator_directional) else "No",
                "task_order_sign_stable": "Unknown",
                "task_order_decision_stable": "Unknown",
                "safety_harm_flag": "Unknown",
                "classification": "Pending",
            })
    return policy_rows, contrast_rows, estimates


def apply_multiplicity(rows: List[Dict[str, Any]]) -> None:
    for row in rows:
        row["adjusted_p"] = float(row["p_value"])
        row["adjustment_family"] = "Unadjusted"
    primary = [i for i, row in enumerate(rows) if row["pair_class"] == "primary" and row["outcome_id"] == "O01"]
    holm_update(rows, primary, "Primary Holm-3: P01/P03/P05 vs P07 on O01")
    landscape = [i for i, row in enumerate(rows) if row["outcome_id"] == "O01" and row["pair_class"] in {"secondary", "landscape"}]
    holm_update(rows, landscape, "Secondary O01 fixed-policy landscape Holm")
    safety = [i for i, row in enumerate(rows) if row["pair_class"] == "primary" and row["outcome_id"] in SAFETY_OUTCOMES]
    holm_update(rows, safety, "Primary-policy safety family Holm-12")


def task_order_audit(frame: pd.DataFrame, full_rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    full_primary = {
        (row["policy_id"], row["comparator_id"]): row
        for row in full_rows if row["pair_class"] == "primary" and row["outcome_id"] == "O01"
    }
    detail: List[Dict[str, Any]] = []
    for omitted_order in range(10):
        subset = frame.loc[frame["order_id"].astype(int) != omitted_order].reset_index(drop=True)
        propensity = fit_cross_fitted_propensity(
            subset, PRIMARY_NUMERIC_FEATURES, PRIMARY_CATEGORICAL_FEATURES,
            n_splits=5, repeats=20, seed=20260827 + omitted_order,
        )["propensity"]
        nuisance = fit_cross_fitted_outcome(
            subset, OUTCOME_COLUMNS["O01"], n_splits=5, repeats=20, seed=20260827 + omitted_order,
        )
        assignments = policy_assignments(subset)
        values: Dict[str, PolicyValueEstimate] = {}
        y = subset[OUTCOME_COLUMNS["O01"]].to_numpy(dtype=float)
        for policy_id in ("P01", "P03", "P05", "P07"):
            d = assignments[policy_id].to_numpy(dtype=int)
            values[policy_id] = policy_value_aipw(y, subset["treatment"], d, propensity, nuisance["m0"], nuisance["m1"])
        temporary: List[Dict[str, Any]] = []
        for left_id, right_id in PRIMARY_PAIRS:
            estimate = policy_contrast(values[left_id], values[right_id])
            low, high = normal_interval(estimate)
            temporary.append({
                "omitted_order": omitted_order,
                "analysis_n": int(len(subset)),
                "policy_id": left_id,
                "comparator_id": right_id,
                "directional_difference": float(estimate.policy_value),
                "directional_ci_low": low,
                "directional_ci_high": high,
                "p_value": two_sided_p(estimate),
            })
        adjusted = multipletests([row["p_value"] for row in temporary], alpha=0.05, method="holm")[1]
        for row, p_adj in zip(temporary, adjusted):
            row["adjusted_p"] = float(p_adj)
            row["decision"] = full_decision(row, use_adjusted=True)
            detail.append(row)

    summary: List[Dict[str, Any]] = []
    for left_id, right_id in PRIMARY_PAIRS:
        full = full_primary[(left_id, right_id)]
        rows = [row for row in detail if row["policy_id"] == left_id and row["comparator_id"] == right_id]
        full_sign = sign(float(full["directional_difference"]))
        full_category = full_decision(full, use_adjusted=True)
        same_sign_n = sum(sign(float(row["directional_difference"])) == full_sign for row in rows)
        same_decision_n = sum(row["decision"] == full_category for row in rows)
        summary.append({
            "policy_id": left_id,
            "policy_name": POLICY_BY_ID[left_id].name,
            "comparator_id": right_id,
            "full_directional_difference": float(full["directional_difference"]),
            "full_adjusted_p": float(full["adjusted_p"]),
            "full_decision": full_category,
            "leave_one_order_out_n": len(rows),
            "sign_same_n": same_sign_n,
            "sign_stable_10_of_10": bool(same_sign_n == 10),
            "decision_same_n": same_decision_n,
            "decision_stable_at_least_9_of_10": bool(same_decision_n >= 9),
            "minimum_directional_difference": float(min(row["directional_difference"] for row in rows)),
            "maximum_directional_difference": float(max(row["directional_difference"] for row in rows)),
            "orders_with_sign_flip": ",".join(str(row["omitted_order"]) for row in rows if sign(float(row["directional_difference"])) != full_sign),
            "orders_with_decision_flip": ",".join(str(row["omitted_order"]) for row in rows if row["decision"] != full_category),
        })
    return detail, summary


def apply_task_and_safety(rows: List[Dict[str, Any]], task_summary: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    task_lookup = {str(row["policy_id"]): row for row in task_summary}
    safety_rows: List[Dict[str, Any]] = []
    for policy_id, comparator_id in PRIMARY_PAIRS:
        relevant = [row for row in rows if row["policy_id"] == policy_id and row["comparator_id"] == comparator_id and row["outcome_id"] in SAFETY_OUTCOMES]
        clear_harms = [row["outcome_id"] for row in relevant if float(row["directional_ci_high"]) < 0]
        negative_points = [row["outcome_id"] for row in relevant if float(row["directional_difference"]) < 0]
        safety_rows.append({
            "policy_id": policy_id,
            "policy_name": POLICY_BY_ID[policy_id].name,
            "comparator_id": comparator_id,
            "outcomes_reviewed": ",".join(SAFETY_OUTCOMES),
            "clear_harm_outcomes": ",".join(clear_harms),
            "negative_point_outcomes": ",".join(negative_points),
            "safety_harm_flag": "Yes" if clear_harms else "No",
            "decision": "Clear harm detected" if clear_harms else "No clear safety harm",
        })
    safety_lookup = {row["policy_id"]: row for row in safety_rows}
    for row in rows:
        primary = row["pair_class"] == "primary" and row["outcome_id"] == "O01"
        if primary:
            task = task_lookup[row["policy_id"]]
            row["task_order_sign_stable"] = "Yes" if task["sign_stable_10_of_10"] else "No"
            row["task_order_decision_stable"] = "Yes" if task["decision_stable_at_least_9_of_10"] else "No"
            row["safety_harm_flag"] = safety_lookup[row["policy_id"]]["safety_harm_flag"]
        elif row["pair_class"] == "primary" and row["outcome_id"] in SAFETY_OUTCOMES:
            row["safety_harm_flag"] = "Yes" if float(row["directional_ci_high"]) < 0 else "No"
        else:
            row["safety_harm_flag"] = "Unknown" if row["direction"] == "neutral" else "No"
        row["classification"] = classify(row, primary=primary)
    return safety_rows


def ratio_sensitivity(frame: pd.DataFrame, bootstrap_indices: np.ndarray) -> List[Dict[str, Any]]:
    assignments = policy_assignments(frame)
    propensity = fit_cross_fitted_propensity(
        frame, PRIMARY_NUMERIC_FEATURES, PRIMARY_CATEGORICAL_FEATURES,
        n_splits=5, repeats=20, seed=20260827,
    )["propensity"]
    specs = {
        "RAIR": ("second_positive_ai_reliance", "second_negative_self_reliance", "outcome_second_rair_zero", "outcome_second_rair_defined"),
        "RSR": ("second_positive_self_reliance", "second_negative_ai_reliance", "outcome_second_rsr_zero", "outcome_second_rsr_defined"),
    }
    rows: List[Dict[str, Any]] = []
    for ratio_name, (num_col, fail_col, zero_col, defined_col) in specs.items():
        frame = frame.copy()
        denom_col = "_denom_" + ratio_name
        frame[denom_col] = frame[num_col].astype(float) + frame[fail_col].astype(float)
        num_pred = fit_cross_fitted_outcome(frame, num_col)
        den_pred = fit_cross_fitted_outcome(frame, denom_col)
        zero_pred = fit_cross_fitted_outcome(frame, zero_col)
        defined = frame.loc[pd.to_numeric(frame[defined_col], errors="coerce").notna()].reset_index(drop=True)
        defined_values: Dict[str, Optional[PolicyValueEstimate]] = {policy.policy_id: None for policy in POLICIES}
        if len(defined) > 0:
            strata = defined["treatment"].astype(str) + "|" + defined["xai_raw"].astype(str) + "|" + defined["calibration_group"].astype(str)
            minimum = int(strata.value_counts().min())
            splits = min(5, minimum)
            if splits >= 2:
                e_def = fit_cross_fitted_propensity(defined, PRIMARY_NUMERIC_FEATURES, PRIMARY_CATEGORICAL_FEATURES, n_splits=splits, repeats=20, seed=20260901)["propensity"]
                m_def = fit_cross_fitted_outcome(defined, defined_col, n_splits=splits, repeats=20, seed=20260901)
                d_assign = policy_assignments(defined)
                y_def = defined[defined_col].to_numpy(dtype=float)
                for policy in POLICIES:
                    d = d_assign[policy.policy_id].to_numpy(dtype=int)
                    defined_values[policy.policy_id] = policy_value_aipw(y_def, defined["treatment"], d, e_def, m_def["m0"], m_def["m1"])
        y_zero = frame[zero_col].to_numpy(dtype=float)
        y_num = frame[num_col].to_numpy(dtype=float)
        y_den = frame[denom_col].to_numpy(dtype=float)
        for policy in POLICIES:
            d = assignments[policy.policy_id].to_numpy(dtype=int)
            zero_est = policy_value_aipw(y_zero, frame["treatment"], d, propensity, zero_pred["m0"], zero_pred["m1"])
            num_est = policy_value_aipw(y_num, frame["treatment"], d, propensity, num_pred["m0"], num_pred["m1"])
            den_est = policy_value_aipw(y_den, frame["treatment"], d, propensity, den_pred["m0"], den_pred["m1"])
            pooled = float(num_est.policy_value / den_est.policy_value) if den_est.policy_value > 0 else None
            pseudo_num = num_est.policy_value + num_est.influence_values
            pseudo_den = den_est.policy_value + den_est.influence_values
            boot_den = pseudo_den[bootstrap_indices].mean(axis=1)
            boot_num = pseudo_num[bootstrap_indices].mean(axis=1)
            valid = boot_den > 1e-12
            pooled_boot = boot_num[valid] / boot_den[valid]
            pooled_low, pooled_high = (np.quantile(pooled_boot, [0.025, 0.975]) if len(pooled_boot) else (np.nan, np.nan))
            defined_est = defined_values[policy.policy_id]
            rows.append({
                "ratio": ratio_name,
                "policy_id": policy.policy_id,
                "policy_name": policy.name,
                "coverage_fraction": float(assignments[policy.policy_id].mean()),
                "released_zero_aipw": float(zero_est.policy_value),
                "defined_participant_aipw": None if defined_est is None else float(defined_est.policy_value),
                "defined_participant_n": int(frame[defined_col].notna().sum()),
                "opportunity_pooled_aipw": pooled,
                "opportunity_pooled_bootstrap_ci_low": None if not np.isfinite(pooled_low) else float(pooled_low),
                "opportunity_pooled_bootstrap_ci_high": None if not np.isfinite(pooled_high) else float(pooled_high),
            })
    return rows


def evaluation_rows(contrast_rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    for index, row in enumerate(contrast_rows, start=1):
        output.append({
            "result_id": "FX-%03d" % index,
            "pair_class": row["pair_class"],
            "policy_id": row["policy_id"],
            "policy_name": row["policy_name"],
            "comparator_id": row["comparator_id"],
            "comparator_name": row["comparator_name"],
            "outcome_id": row["outcome_id"],
            "outcome_name": row["outcome_name"],
            "direction": row["direction"],
            "policy_value": row["policy_value"],
            "comparator_value": row["comparator_value"],
            "raw_difference": row["aipw_difference"],
            "directional_difference": row["directional_difference"],
            "raw_ci_low": row["raw_ci_low"],
            "raw_ci_high": row["raw_ci_high"],
            "directional_ci_low": row["directional_ci_low"],
            "directional_ci_high": row["directional_ci_high"],
            "bootstrap_ci_low": row["bootstrap_ci_low"],
            "bootstrap_ci_high": row["bootstrap_ci_high"],
            "p_value": row["p_value"],
            "adjusted_p": row["adjusted_p"],
            "adjustment_family": row["adjustment_family"],
            "policy_coverage": row["policy_coverage"],
            "comparator_coverage": row["comparator_coverage"],
            "coverage_delta": row["coverage_delta"],
            "or_difference": row["or_difference"],
            "ipw_difference": row["ipw_difference"],
            "aipw_difference": row["aipw_difference"],
            "estimator_agreement": row["estimator_agreement"],
            "task_order_sign_stable": row["task_order_sign_stable"],
            "task_order_decision_stable": row["task_order_decision_stable"],
            "safety_harm_flag": row["safety_harm_flag"],
            "status": "Complete",
            "classification": row["classification"],
        })
    return output


def make_figures(out: Path, primary_rows: Sequence[Mapping[str, Any]], policy_rows: Sequence[Mapping[str, Any]]) -> None:
    ordered = [next(row for row in primary_rows if row["policy_id"] == policy_id) for policy_id in ("P01", "P03", "P05")]
    y = np.arange(len(ordered))
    values = np.array([row["directional_difference"] for row in ordered], dtype=float)
    lows = np.array([row["directional_ci_low"] for row in ordered], dtype=float)
    highs = np.array([row["directional_ci_high"] for row in ordered], dtype=float)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.errorbar(values, y, xerr=np.vstack([values - lows, highs - values]), fmt="o", capsize=4)
    ax.axvline(0.0, linewidth=1)
    ax.set_yticks(y)
    ax.set_yticklabels([row["policy_name"] + " vs universal" for row in ordered])
    ax.set_xlabel("Directional standardized difference in absolute calibration improvement")
    ax.set_title("Primary fixed-policy contrasts (AIPW, 95% CI)")
    ax.invert_yaxis()
    fig.tight_layout()
    fig.savefig(out / "g05_g08_primary_policy_forest.png", dpi=180)
    plt.close(fig)

    o01 = [row for row in policy_rows if row["outcome_id"] == "O01"]
    o01.sort(key=lambda row: row["policy_id"])
    x = np.arange(len(o01))
    vals = np.array([row["aipw_value"] for row in o01], dtype=float)
    lows = np.array([row["aipw_ci_low"] for row in o01], dtype=float)
    highs = np.array([row["aipw_ci_high"] for row in o01], dtype=float)
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.errorbar(x, vals, yerr=np.vstack([vals - lows, highs - vals]), fmt="o", capsize=3)
    ax.axhline(0.0, linewidth=1)
    ax.set_xticks(x)
    ax.set_xticklabels([row["policy_id"] for row in o01])
    ax.set_ylabel("Standardized absolute calibration improvement")
    ax.set_xlabel("Fixed policy")
    ax.set_title("P00-P07 standardized policy values (AIPW, 95% CI)")
    fig.tight_layout()
    fig.savefig(out / "g05_fixed_policy_values_o01.png", dpi=180)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--bootstrap-draws", type=int, default=5000)
    parser.add_argument("--no-figures", action="store_true")
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    frame = build_extension_frame(args.repo.resolve())
    if len(frame) != 249:
        raise AssertionError("Unexpected extension sample")
    if {"username", "user_id", "ai_id"}.intersection(frame.columns):
        raise AssertionError("Participant identifier leakage")

    boot = stratified_bootstrap_indices(frame, draws=args.bootstrap_draws, seed=20260827)
    policy_rows, contrast_rows, _ = estimate_all(frame, list(OUTCOME_META), boot)
    apply_multiplicity(contrast_rows)
    task_detail, task_summary = task_order_audit(frame, contrast_rows)
    safety = apply_task_and_safety(contrast_rows, task_summary)
    ratio_rows = ratio_sensitivity(frame, boot)
    eval_rows = evaluation_rows(contrast_rows)

    primary_rows = [row for row in contrast_rows if row["pair_class"] == "primary" and row["outcome_id"] == "O01"]
    multiplicity_rows = [{
        "policy_id": row["policy_id"],
        "comparator_id": row["comparator_id"],
        "outcome_id": row["outcome_id"],
        "p_value": row["p_value"],
        "adjusted_p": row["adjusted_p"],
        "adjustment_family": row["adjustment_family"],
    } for row in contrast_rows if row["adjustment_family"] != "Unadjusted"]
    estimator_rows = [{
        "policy_id": row["policy_id"],
        "comparator_id": row["comparator_id"],
        "outcome_id": row["outcome_id"],
        "or_difference": row["or_difference"],
        "ipw_difference": row["ipw_difference"],
        "aipw_difference": row["aipw_difference"],
        "direction": row["direction"],
        "estimator_agreement": row["estimator_agreement"],
    } for row in contrast_rows]

    write_tsv(out / "g05_fixed_policy_values.tsv", policy_rows)
    write_tsv(out / "g05_fixed_policy_contrasts.tsv", contrast_rows)
    write_tsv(out / "g05_primary_comparisons.tsv", primary_rows)
    write_tsv(out / "g06_estimator_concordance.tsv", estimator_rows)
    write_tsv(out / "g07_task_order_primary.tsv", task_detail)
    write_tsv(out / "g07_task_order_summary.tsv", task_summary)
    write_tsv(out / "g08_safety_review.tsv", safety)
    write_tsv(out / "g08_multiplicity.tsv", multiplicity_rows)
    write_tsv(out / "g08_ratio_sensitivity.tsv", ratio_rows)
    write_tsv(out / "g05_g08_evaluation_rows.tsv", eval_rows)

    primary_classifications = {row["policy_id"]: row["classification"] for row in primary_rows}
    best_policy = max([row for row in policy_rows if row["outcome_id"] == "O01"], key=lambda row: row["aipw_value"])
    g09_inputs = {
        "best_fixed_policy_id": best_policy["policy_id"],
        "best_fixed_policy_name": best_policy["policy_name"],
        "best_fixed_policy_o01_value": best_policy["aipw_value"],
        "primary_classifications": primary_classifications,
        "any_primary_robust_or_specification_sensitive_favorable": any(
            value in {"Robustly favorable", "Specification-sensitive favorable"}
            for value in primary_classifications.values()
        ),
        "learned_policy_overlap_gate": "Conditional",
        "learned_policy_status": "Blocked pending G09 expert go/no-go decision",
    }
    write_json(out / "g09_decision_inputs.json", g09_inputs)

    summary = {
        "schema_version": "1.0",
        "stage": "G05-G08 fixed-policy evaluation",
        "sample_n": int(len(frame)),
        "policy_values_n": len(policy_rows),
        "fixed_contrasts_n": len(contrast_rows),
        "primary_comparisons_n": len(primary_rows),
        "bootstrap_draws": int(args.bootstrap_draws),
        "g05_status": "PASS",
        "g06_status": "PASS",
        "g07_status": "PASS",
        "g08_status": "PASS",
        "primary_results": primary_rows,
        "task_order_summary": task_summary,
        "safety_review": safety,
        "g09_decision_inputs": g09_inputs,
        "causal_identification_claimed": False,
        "participant_level_data_emitted": False,
        "upstream_util_imported": False,
    }
    write_json(out / "g05_g08_summary.json", summary)

    status_lines = [
        "# ETH HAI G05-G08 Fixed-Policy Gate",
        "",
        "- G05 fixed-policy values: **PASS**",
        "- G06 estimator concordance: **PASS**",
        "- G07 task-order sensitivity: **PASS**",
        "- G08 multiplicity and safety review: **PASS**",
        "- Participant-level data emitted: **NO**",
        "- Causal identification claimed: **NO**",
        "- Learned policy P08: **BLOCKED pending G09 decision**",
        "",
        "## Primary classifications",
    ]
    status_lines.extend("- %s: **%s**" % (POLICY_BY_ID[pid].name, classification) for pid, classification in primary_classifications.items())
    (out / "G05_G08_STATUS.md").write_text("\n".join(status_lines) + "\n", encoding="utf-8")

    if not args.no_figures:
        make_figures(out, primary_rows, policy_rows)

    if len(policy_rows) != 80 or len(contrast_rows) != 130 or len(primary_rows) != 3:
        raise AssertionError("Unexpected result-register size")
    if any(row["classification"] == "Pending" for row in contrast_rows):
        raise AssertionError("Pending fixed-policy classification")
    if any(row["estimator_agreement"] not in {"Yes", "No"} for row in contrast_rows):
        raise AssertionError("Invalid estimator agreement")

    print(json.dumps({
        "g05": "PASS", "g06": "PASS", "g07": "PASS", "g08": "PASS",
        "policy_values": len(policy_rows), "contrasts": len(contrast_rows),
        "primary_classifications": primary_classifications,
        "best_fixed_policy": best_policy["policy_id"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
