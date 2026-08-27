#!/usr/bin/env python3
"""Post-G10 regression-to-the-mean and precision addendum.

This separately versioned analysis does not alter the frozen direct,
robustness, or extension registers. It emits aggregate tables only and never
writes participant-level rows or identifiers.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
from pathlib import Path
from typing import Dict, List, Mapping, Sequence, Tuple

import numpy as np
import pandas as pd
from scipy import stats

from eth_hai_clean.core import TASK_ORDERS, load_task_answers, load_valid_participants
from eth_hai_extension.core import (
    POLICIES,
    PRIMARY_CATEGORICAL_FEATURES,
    PRIMARY_NUMERIC_FEATURES,
    build_extension_frame,
    policy_assignments,
)
from eth_hai_extension.estimators import fit_cross_fitted_nuisance, policy_value_aipw

SEED = 20260827
DRAWS = 20000

FROZEN_PRIMARY_COMPARISONS = (
    {
        "policy_id": "P01",
        "policy_name": "Underestimators only",
        "analysis_n": 249,
        "directional_difference": -0.008597504993811005,
        "standard_error": 0.11233849562408539,
        "ci_low": -0.22877694841602894,
        "ci_high": 0.21158193842840693,
    },
    {
        "policy_id": "P03",
        "policy_name": "Overestimators only",
        "analysis_n": 249,
        "directional_difference": -0.10833637411693442,
        "standard_error": 0.11621665870959805,
        "ci_low": -0.3361168271873266,
        "ci_high": 0.11944407895345776,
    },
    {
        "policy_id": "P05",
        "policy_name": "All miscalibrated",
        "analysis_n": 249,
        "directional_difference": -0.01974037314819156,
        "standard_error": 0.07489960214484795,
        "ci_low": -0.16654159255809344,
        "ci_high": 0.1270608462617103,
    },
)
FROZEN_ANCHOR_P07_VS_P00 = 0.09719300510655185


def json_default(value):
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    raise TypeError(type(value).__name__)


def write_tsv(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    fields = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: "" if row.get(key) is None else row.get(key) for key in fields})


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=json_default) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def target_masks(frame: pd.DataFrame) -> Dict[str, pd.Series]:
    group = frame["calibration_group"]
    return {
        "Underestimation": group == "Underestimation",
        "Overestimation": group == "Overestimation",
        "All miscalibrated": group != "Accurate",
    }


def metric_specs() -> Dict[str, Dict[str, object]]:
    return {
        "signed_calibration_gap": {
            "first": "miscalibration_first", "second": "miscalibration_second",
            "change": "second_minus_first", "lower": -6.0, "upper": 6.0,
        },
        "absolute_calibration_improvement": {
            "first": "miscalibration_first", "second": "miscalibration_second",
            "change": "absolute_improvement", "lower": -6.0, "upper": 6.0,
        },
        "accuracy": {
            "first": "first_accuracy", "second": "second_accuracy",
            "change": "second_minus_first", "lower": 0.0, "upper": 1.0,
        },
        "accuracy_wid": {
            "first": "first_appropriate_reliance", "second": "second_appropriate_reliance",
            "change": "second_minus_first", "lower": 0.0, "upper": 1.0,
        },
        "rair_released_zero": {
            "first": "first_rair", "second": "second_rair",
            "change": "second_minus_first", "lower": 0.0, "upper": 1.0,
        },
        "rsr_released_zero": {
            "first": "first_rsr", "second": "second_rsr",
            "change": "second_minus_first", "lower": 0.0, "upper": 1.0,
        },
    }


def compute_change(first: np.ndarray, second: np.ndarray, kind: str) -> np.ndarray:
    if kind == "absolute_improvement":
        return np.abs(first) - np.abs(second)
    return second - first


def bootstrap_mean_ci(values: np.ndarray, rng: np.random.Generator) -> Tuple[float, float, float, float]:
    values = np.asarray(values, float)
    n = len(values)
    indices = rng.integers(0, n, size=(DRAWS, n))
    means = values[indices].mean(axis=1)
    low, high = np.quantile(means, [0.025, 0.975])
    p = 2.0 * min(float(np.mean(means <= 0.0)), float(np.mean(means >= 0.0)))
    return float(values.mean()), float(low), float(high), min(1.0, p)


def observed_change_rows(frame: pd.DataFrame, rng: np.random.Generator):
    rows: List[Dict[str, object]] = []
    differences: List[Dict[str, object]] = []
    specs = metric_specs()
    masks = target_masks(frame)
    samples = {
        "Tutorial observed": frame["treatment"] == 1,
        "No tutorial observed": frame["treatment"] == 0,
    }
    cache: Dict[Tuple[str, str, str], np.ndarray] = {}
    for sample_name, sample_mask in samples.items():
        for group_name, group_mask in masks.items():
            mask = sample_mask & group_mask
            for metric, spec in specs.items():
                first = pd.to_numeric(frame.loc[mask, spec["first"]], errors="coerce").to_numpy(float)
                second = pd.to_numeric(frame.loc[mask, spec["second"]], errors="coerce").to_numpy(float)
                valid = np.isfinite(first) & np.isfinite(second)
                first, second = first[valid], second[valid]
                changes = compute_change(first, second, str(spec["change"]))
                estimate, low, high, p = bootstrap_mean_ci(changes, rng)
                rows.append({
                    "sample": sample_name,
                    "calibration_group": group_name,
                    "metric": metric,
                    "n": len(changes),
                    "first_mean": float(first.mean()),
                    "second_mean": float(second.mean()),
                    "mean_change": estimate,
                    "bootstrap_ci_low": low,
                    "bootstrap_ci_high": high,
                    "bootstrap_p_two_sided": p,
                    "change_definition": spec["change"],
                })
                cache[(sample_name, group_name, metric)] = changes
    for group_name in masks:
        for metric in specs:
            tutorial = cache[("Tutorial observed", group_name, metric)]
            control = cache[("No tutorial observed", group_name, metric)]
            t_idx = rng.integers(0, len(tutorial), size=(DRAWS, len(tutorial)))
            c_idx = rng.integers(0, len(control), size=(DRAWS, len(control)))
            boot = tutorial[t_idx].mean(axis=1) - control[c_idx].mean(axis=1)
            low, high = np.quantile(boot, [0.025, 0.975])
            p = 2.0 * min(float(np.mean(boot <= 0.0)), float(np.mean(boot >= 0.0)))
            differences.append({
                "calibration_group": group_name,
                "metric": metric,
                "tutorial_n": len(tutorial),
                "no_tutorial_n": len(control),
                "tutorial_mean_change": float(tutorial.mean()),
                "no_tutorial_mean_change": float(control.mean()),
                "tutorial_minus_no_tutorial": float(tutorial.mean() - control.mean()),
                "bootstrap_ci_low": float(low),
                "bootstrap_ci_high": float(high),
                "bootstrap_p_two_sided": min(1.0, p),
            })
    return rows, differences


def fit_linear(first: np.ndarray, second: np.ndarray) -> Dict[str, object]:
    valid = np.isfinite(first) & np.isfinite(second)
    x, y = first[valid].astype(float), second[valid].astype(float)
    design = np.column_stack([np.ones(len(x)), x])
    intercept, slope = np.linalg.lstsq(design, y, rcond=None)[0]
    residual = y - (intercept + slope * x)
    residual = residual - residual.mean()
    correlation = float(np.corrcoef(x, y)[0, 1]) if np.std(x) and np.std(y) else math.nan
    return {
        "n": len(x), "intercept": float(intercept), "slope": float(slope),
        "correlation": correlation, "residual_sd": float(np.std(residual, ddof=1)),
        "residuals": residual,
    }


def rtm_null_rows(frame: pd.DataFrame, rng: np.random.Generator):
    model_rows: List[Dict[str, object]] = []
    null_rows: List[Dict[str, object]] = []
    specs = metric_specs()
    tutorial = frame["treatment"] == 1
    references = {
        "No tutorial reference": frame["treatment"] == 0,
        "All-participant reference": pd.Series(True, index=frame.index),
    }
    for ref_name, ref_mask in references.items():
        for metric, spec in specs.items():
            x_ref = pd.to_numeric(frame.loc[ref_mask, spec["first"]], errors="coerce").to_numpy(float)
            y_ref = pd.to_numeric(frame.loc[ref_mask, spec["second"]], errors="coerce").to_numpy(float)
            fit = fit_linear(x_ref, y_ref)
            model_rows.append({
                "reference": ref_name, "metric": metric, "n": fit["n"],
                "first_mean": float(np.nanmean(x_ref)), "second_mean": float(np.nanmean(y_ref)),
                "correlation": fit["correlation"], "intercept": fit["intercept"],
                "slope": fit["slope"], "residual_sd": fit["residual_sd"],
            })
            residuals = np.asarray(fit["residuals"], float)
            for group_name, group_mask in target_masks(frame).items():
                mask = tutorial & group_mask
                first = pd.to_numeric(frame.loc[mask, spec["first"]], errors="coerce").to_numpy(float)
                second = pd.to_numeric(frame.loc[mask, spec["second"]], errors="coerce").to_numpy(float)
                valid = np.isfinite(first) & np.isfinite(second)
                first, second = first[valid], second[valid]
                pred = float(fit["intercept"]) + float(fit["slope"]) * first
                idx = rng.integers(0, len(residuals), size=(DRAWS, len(first)))
                sim_second = pred[None, :] + residuals[idx]
                sim_second = np.clip(sim_second, float(spec["lower"]), float(spec["upper"]))
                sim_change = compute_change(first[None, :], sim_second, str(spec["change"])).mean(axis=1)
                observed = float(compute_change(first, second, str(spec["change"])).mean())
                null_mean = float(sim_change.mean())
                low, high = np.quantile(sim_change, [0.025, 0.975])
                excess = observed - null_mean
                centered = sim_change - null_mean
                p = float(np.mean(np.abs(centered) >= abs(excess)))
                null_rows.append({
                    "reference": ref_name,
                    "target_sample": "Tutorial observed",
                    "calibration_group": group_name,
                    "metric": metric,
                    "n": len(first),
                    "observed_change": observed,
                    "rtm_null_mean": null_mean,
                    "rtm_null_ci_low": float(low),
                    "rtm_null_ci_high": float(high),
                    "observed_minus_null": excess,
                    "empirical_p_two_sided": p,
                    "change_definition": spec["change"],
                })
    return model_rows, null_rows


def split_half_reliability(repo: Path):
    participants = load_valid_participants(repo).reset_index(drop=True)
    answers = load_task_answers(repo)
    groups = {
        "All participants": np.ones(len(participants), dtype=bool),
        "Tutorial observed": participants["tutorial"].astype(int).to_numpy() == 0,
        "No tutorial observed": participants["tutorial"].astype(int).to_numpy() == 1,
    }
    splits = [combo for combo in itertools.combinations(range(6), 3) if 0 in combo]
    rows: List[Dict[str, object]] = []
    for split_id, side_a in enumerate(splits, 1):
        side_b = tuple(i for i in range(6) if i not in side_a)
        a_scores, b_scores = [], []
        for _, row in participants.iterrows():
            sequence = TASK_ORDERS[int(row["question_order"])][:6]
            correct = [float(str(row["advice%d" % task_id]) == answers[int(task_id)][0]) for task_id in sequence]
            a_scores.append(float(np.mean([correct[i] for i in side_a])))
            b_scores.append(float(np.mean([correct[i] for i in side_b])))
        a, b = np.asarray(a_scores), np.asarray(b_scores)
        for sample_name, mask in groups.items():
            aa, bb = a[mask], b[mask]
            correlation = float(np.corrcoef(aa, bb)[0, 1]) if np.std(aa) and np.std(bb) else math.nan
            sb = float(2.0 * correlation / (1.0 + correlation)) if np.isfinite(correlation) and correlation > -1.0 else math.nan
            rows.append({
                "split_id": split_id,
                "positions_a": ",".join(str(i + 1) for i in side_a),
                "positions_b": ",".join(str(i + 1) for i in side_b),
                "sample": sample_name, "n": int(mask.sum()),
                "half_correlation": correlation,
                "spearman_brown_reliability": sb,
            })
    overall = [r for r in rows if r["sample"] == "All participants"]
    summary = {
        "splits": len(splits),
        "all_participants_half_correlation_mean": float(np.nanmean([r["half_correlation"] for r in overall])),
        "all_participants_half_correlation_min": float(np.nanmin([r["half_correlation"] for r in overall])),
        "all_participants_half_correlation_max": float(np.nanmax([r["half_correlation"] for r in overall])),
        "all_participants_spearman_brown_mean": float(np.nanmean([r["spearman_brown_reliability"] for r in overall])),
        "calibration_split_half_identifiable": False,
        "reason": "Only one self-assessment was collected for the full six-task batch; no half-specific self-assessment exists.",
    }
    return rows, summary


def mde_rows(power: float = 0.80):
    anchor = abs(FROZEN_ANCHOR_P07_VS_P00)
    z_power = stats.norm.ppf(power)
    alphas = {
        "unadjusted_0.05": 0.05,
        "holm_first_step_0.016667": 0.05 / 3.0,
        "source_fixed_0.0125": 0.0125,
    }
    rows: List[Dict[str, object]] = []
    for frozen in FROZEN_PRIMARY_COMPARISONS:
        se = float(frozen["standard_error"])
        n = int(frozen["analysis_n"])
        row: Dict[str, object] = {
            "policy_id": frozen["policy_id"], "policy_name": frozen["policy_name"],
            "analysis_n": n, "observed_directional_difference": frozen["directional_difference"],
            "standard_error": se, "normal_ci_low": frozen["ci_low"], "normal_ci_high": frozen["ci_high"],
            "anchor_universal_vs_none": anchor,
        }
        for label, alpha in alphas.items():
            mde = float((stats.norm.ppf(1.0 - alpha / 2.0) + z_power) * se)
            row["mde_80pct_%s" % label] = mde
            row["mde_to_anchor_%s" % label] = mde / anchor
            row["approx_n_for_anchor_%s" % label] = int(math.ceil(n * (mde / anchor) ** 2))
            row["approx_n_for_0_05_%s" % label] = int(math.ceil(n * (mde / 0.05) ** 2))
        rows.append(row)
    return rows, {
        "power": power,
        "anchor_directional_difference": anchor,
        "interpretation": "MDEs are normal-approximation arithmetic on frozen SEs; sample-size projections assume SE scales as 1/sqrt(n). Holm has no single fixed per-test alpha, so the first-step 0.05/3 threshold is shown conservatively.",
        "frozen_values_source": "G05 primary comparison register and P07-versus-P00 O01 anchor",
    }


def ratio_count_rows(frame: pd.DataFrame):
    assignments = policy_assignments(frame)
    n = len(frame)
    rows: List[Dict[str, object]] = []
    specs = {
        "RAIR": ("second_positive_ai_reliance", "second_negative_self_reliance"),
        "RSR": ("second_positive_self_reliance", "second_negative_ai_reliance"),
    }
    for ratio, (positive, negative) in specs.items():
        num_col = "postg10_%s_numerator" % ratio.lower()
        den_col = "postg10_%s_opportunities" % ratio.lower()
        def_col = "postg10_%s_defined" % ratio.lower()
        frame[num_col] = pd.to_numeric(frame[positive], errors="raise").astype(float)
        frame[den_col] = frame[num_col] + pd.to_numeric(frame[negative], errors="raise").astype(float)
        frame[def_col] = (frame[den_col] > 0).astype(float)
        fits = {
            name: fit_cross_fitted_nuisance(frame, column, PRIMARY_NUMERIC_FEATURES, PRIMARY_CATEGORICAL_FEATURES)
            for name, column in {"numerator": num_col, "denominator": den_col, "defined": def_col}.items()
        }
        outcomes = {"numerator": num_col, "denominator": den_col, "defined": def_col}
        for policy in POLICIES:
            d = assignments[policy.policy_id].to_numpy(int)
            estimates = {}
            for name, column in outcomes.items():
                fit = fits[name]
                estimates[name] = policy_value_aipw(
                    frame[column].to_numpy(float), frame["treatment"].to_numpy(int), d,
                    fit["propensity"], fit["m0"], fit["m1"],
                )
            numerator = estimates["numerator"].policy_value
            denominator = estimates["denominator"].policy_value
            rows.append({
                "ratio": ratio,
                "policy_id": policy.policy_id,
                "policy_name": policy.name,
                "policy_coverage_n": int(d.sum()),
                "standardized_numerator_per_participant": numerator,
                "standardized_opportunities_per_participant": denominator,
                "standardized_defined_fraction": estimates["defined"].policy_value,
                "standardized_numerator_total_n249": numerator * n,
                "standardized_opportunity_total_n249": denominator * n,
                "standardized_defined_n_n249": estimates["defined"].policy_value * n,
                "opportunity_pooled_ratio": numerator / denominator if denominator > 0 else math.nan,
            })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    frame = build_extension_frame(repo)
    if len(frame) != 249:
        raise AssertionError("Unexpected analytic sample")
    rng = np.random.default_rng(SEED)

    observed, differences = observed_change_rows(frame, rng)
    reference_models, null_rows = rtm_null_rows(frame, rng)
    split_rows, split_summary = split_half_reliability(repo)
    precision_rows, precision_summary = mde_rows()
    ratio_rows = ratio_count_rows(frame)

    write_tsv(out / "postg10_observed_group_changes.tsv", observed)
    write_tsv(out / "postg10_tutorial_minus_no_tutorial_changes.tsv", differences)
    write_tsv(out / "postg10_rtm_reference_models.tsv", reference_models)
    write_tsv(out / "postg10_rtm_simulation_null.tsv", null_rows)
    write_tsv(out / "postg10_split_half_reliability.tsv", split_rows)
    write_json(out / "postg10_split_half_summary.json", split_summary)
    write_tsv(out / "postg10_primary_precision_mde.tsv", precision_rows)
    write_json(out / "postg10_precision_summary.json", precision_summary)
    write_tsv(out / "postg10_ratio_numerator_opportunities.tsv", ratio_rows)

    def find_null(group: str, metric: str):
        return next(r for r in null_rows if r["reference"] == "No tutorial reference" and r["calibration_group"] == group and r["metric"] == metric)

    summary = {
        "schema_version": "1.0",
        "stage": "registered post-G10 addendum",
        "sample_n": len(frame),
        "simulation_draws": DRAWS,
        "seed": SEED,
        "frozen_registers_modified": False,
        "participant_level_data_emitted": False,
        "learned_policy_fitted": False,
        "split_half": split_summary,
        "precision": precision_summary,
        "selected_rtm_results": {
            "under_accuracy": find_null("Underestimation", "accuracy"),
            "under_accuracy_wid": find_null("Underestimation", "accuracy_wid"),
            "under_rair": find_null("Underestimation", "rair_released_zero"),
            "under_rsr": find_null("Underestimation", "rsr_released_zero"),
            "all_miscalibrated_abs_gap": find_null("All miscalibrated", "absolute_calibration_improvement"),
            "under_abs_gap": find_null("Underestimation", "absolute_calibration_improvement"),
            "over_abs_gap": find_null("Overestimation", "absolute_calibration_improvement"),
        },
    }
    write_json(out / "postg10_addendum_summary.json", summary)
    (out / "POST_G10_STATUS.md").write_text(
        "# Post-G10 RTM and Precision Addendum\n\n"
        "- Execution: **PASS**\n"
        "- Analytic sample: **249**\n"
        "- Frozen registers modified: **NO**\n"
        "- Participant-level data emitted: **NO**\n"
        "- Learned policy fitted: **NO**\n"
        "- Split-half calibration groups: **NOT IDENTIFIABLE** (one self-assessment per six-task batch)\n",
        encoding="utf-8",
    )
    print(json.dumps({"passed": True, "sample_n": len(frame), "simulation_draws": DRAWS}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
