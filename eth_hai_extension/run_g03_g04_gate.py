#!/usr/bin/env python3
"""Run G03 positivity and G04 implementation/leakage gates.

The workflow emits aggregate diagnostics only. It does not estimate source-data
policy values, emit participant rows, or retain participant identifiers.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from eth_hai_extension.core import (
    CALIBRATION_ORDER,
    DEFINED_RATIO_OUTCOMES,
    OUTCOME_COLUMNS,
    POLICIES,
    PRIMARY_CATEGORICAL_FEATURES,
    PRIMARY_FEATURES,
    PRIMARY_NUMERIC_FEATURES,
    SENSITIVITY_FEATURES,
    build_extension_frame,
    outcome_registry_summary,
    policy_assignments,
    policy_coverage,
    validate_feature_registry,
)
from eth_hai_extension.estimators import (
    clip_propensity,
    fit_cross_fitted_propensity,
    policy_contrast,
    policy_value_aipw,
    policy_value_ipw,
    policy_value_or,
    repeated_stratified_folds,
)

EXPECTED_POLICY_COVERAGE = {
    "P00": 0,
    "P01": 72,
    "P02": 76,
    "P03": 101,
    "P04": 148,
    "P05": 173,
    "P06": 177,
    "P07": 249,
}


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


def count_by(frame: pd.DataFrame, columns: Sequence[str]) -> List[Dict[str, Any]]:
    grouped = frame.groupby(list(columns) + ["treatment"], dropna=False).size().unstack(fill_value=0)
    rows: List[Dict[str, Any]] = []
    for index, values in grouped.sort_index().iterrows():
        if not isinstance(index, tuple):
            index = (index,)
        row = {column: index[position] for position, column in enumerate(columns)}
        no_tutorial = int(values.get(0, 0))
        tutorial = int(values.get(1, 0))
        row.update({
            "no_tutorial_n": no_tutorial,
            "tutorial_n": tutorial,
            "total_n": no_tutorial + tutorial,
            "both_arms_observed": bool(no_tutorial > 0 and tutorial > 0),
            "minimum_arm_n": min(no_tutorial, tutorial),
        })
        rows.append(row)
    return rows


def policy_support_rows(frame: pd.DataFrame) -> List[Dict[str, Any]]:
    assignments = policy_assignments(frame)
    rows: List[Dict[str, Any]] = []
    actual = frame["treatment"].astype(int)
    for policy in POLICIES:
        d = assignments[policy.policy_id].astype(int)
        regions: Dict[int, Dict[int, int]] = {}
        nonempty_region_arm_counts: List[int] = []
        all_nonempty_regions_have_both = True
        for decision in (0, 1):
            mask = d == decision
            counts = {
                0: int(((actual == 0) & mask).sum()),
                1: int(((actual == 1) & mask).sum()),
            }
            regions[decision] = counts
            if int(mask.sum()) > 0:
                nonempty_region_arm_counts.extend([counts[0], counts[1]])
                if counts[0] == 0 or counts[1] == 0:
                    all_nonempty_regions_have_both = False
        min_count = min(nonempty_region_arm_counts) if nonempty_region_arm_counts else 0
        rows.append({
            "policy_id": policy.policy_id,
            "policy_name": policy.name,
            "coverage_n": int(d.sum()),
            "coverage_fraction": float(d.mean()),
            "no_treat_region_n": int((d == 0).sum()),
            "no_treat_region_actual_no_tutorial_n": regions[0][0],
            "no_treat_region_actual_tutorial_n": regions[0][1],
            "treat_region_n": int((d == 1).sum()),
            "treat_region_actual_no_tutorial_n": regions[1][0],
            "treat_region_actual_tutorial_n": regions[1][1],
            "observed_assignment_matches_policy_n": int((actual == d).sum()),
            "minimum_nonempty_region_arm_n": int(min_count),
            "both_actual_arms_in_each_nonempty_region": bool(all_nonempty_regions_have_both),
            "g03_fixed_policy_support": "Supported" if all_nonempty_regions_have_both else "Not supported",
        })
    return rows


def qcut_labels(values: pd.Series, prefix: str) -> pd.Series:
    ranked = pd.to_numeric(values, errors="raise").rank(method="first")
    bins = pd.qcut(ranked, q=4, labels=[prefix + "1", prefix + "2", prefix + "3", prefix + "4"])
    return bins.astype(str)


def feature_overlap_rows(frame: pd.DataFrame) -> List[Dict[str, Any]]:
    features: List[Tuple[str, pd.Series]] = [
        ("first_correct_count", frame["first_correct_count"].astype(int).astype(str)),
        ("miscalibration_first", frame["miscalibration_first"].astype(int).astype(str)),
        ("abs_miscalibration_first", frame["abs_miscalibration_first"].astype(int).astype(str)),
        ("ati_quartile", qcut_labels(frame["ati"], "Q")),
        ("propensity_quartile", qcut_labels(frame["propensity"], "Q")),
        ("trust_first_quartile", qcut_labels(frame["trust_first"], "Q")),
    ]
    rows: List[Dict[str, Any]] = []
    for feature, bins in features:
        temp = pd.DataFrame({"bin": bins, "treatment": frame["treatment"].astype(int)})
        grouped = temp.groupby(["bin", "treatment"]).size().unstack(fill_value=0)
        for bin_value, counts in grouped.sort_index().iterrows():
            no_n = int(counts.get(0, 0))
            yes_n = int(counts.get(1, 0))
            rows.append({
                "feature": feature,
                "bin": str(bin_value),
                "no_tutorial_n": no_n,
                "tutorial_n": yes_n,
                "total_n": no_n + yes_n,
                "both_arms_observed": bool(no_n > 0 and yes_n > 0),
                "minimum_arm_n": min(no_n, yes_n),
            })
    return rows


def propensity_summary_rows(frame: pd.DataFrame, e: np.ndarray) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    quantiles = [0.0, 0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99, 1.0]
    for label, mask in (
        ("all", np.ones(len(frame), dtype=bool)),
        ("observed_no_tutorial", frame["treatment"].to_numpy(dtype=int) == 0),
        ("observed_tutorial", frame["treatment"].to_numpy(dtype=int) == 1),
    ):
        values = np.asarray(e[mask], dtype=float)
        q = np.quantile(values, quantiles)
        row: Dict[str, Any] = {"group": label, "n": int(len(values)), "mean": float(np.mean(values)), "sd": float(np.std(values, ddof=1))}
        for probability, value in zip(quantiles, q):
            row["q_%04d" % int(round(probability * 10000))] = float(value)
        row.update({
            "below_0_05_n": int(np.sum(values < 0.05)),
            "above_0_95_n": int(np.sum(values > 0.95)),
            "below_0_10_n": int(np.sum(values < 0.10)),
            "above_0_90_n": int(np.sum(values > 0.90)),
        })
        rows.append(row)

    actual = frame["treatment"].to_numpy(dtype=int)
    clipped = clip_propensity(e)
    weights = actual / clipped + (1 - actual) / (1.0 - clipped)

    def ess(values: np.ndarray) -> float:
        return float(np.sum(values) ** 2 / np.sum(values ** 2))

    min_treated = float(np.min(e[actual == 1]))
    max_treated = float(np.max(e[actual == 1]))
    min_control = float(np.min(e[actual == 0]))
    max_control = float(np.max(e[actual == 0]))
    overlap_low = max(min_treated, min_control)
    overlap_high = min(max_treated, max_control)
    summary = {
        "cross_fitted_model": "L2-regularized logistic regression; 5 folds x 20 repeats",
        "propensity_interpretation": "descriptive assignment-overlap diagnostic; not a causal design probability",
        "minimum": float(np.min(e)),
        "maximum": float(np.max(e)),
        "common_empirical_range_low": overlap_low,
        "common_empirical_range_high": overlap_high,
        "common_empirical_range_nonempty": bool(overlap_low <= overlap_high),
        "outside_0_05_0_95_n": int(np.sum((e < 0.05) | (e > 0.95))),
        "outside_0_10_0_90_n": int(np.sum((e < 0.10) | (e > 0.90))),
        "ipw_effective_sample_size_all": ess(weights),
        "ipw_effective_sample_size_no_tutorial": ess(weights[actual == 0]),
        "ipw_effective_sample_size_tutorial": ess(weights[actual == 1]),
    }
    return rows, summary


def fold_audit_rows(frame: pd.DataFrame) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for repeat, fold, train_index, test_index in repeated_stratified_folds(frame, n_splits=5, repeats=20, seed=20260827):
        test = frame.iloc[test_index]
        treatment_counts = test["treatment"].value_counts().to_dict()
        group_counts = test["calibration_group"].value_counts().to_dict()
        xai_counts = test["xai_raw"].value_counts().to_dict()
        rows.append({
            "repeat": repeat,
            "fold": fold,
            "train_n": int(len(train_index)),
            "test_n": int(len(test_index)),
            "test_no_tutorial_n": int(treatment_counts.get(0, 0)),
            "test_tutorial_n": int(treatment_counts.get(1, 0)),
            "test_under_n": int(group_counts.get("Underestimation", 0)),
            "test_accurate_n": int(group_counts.get("Accurate", 0)),
            "test_over_n": int(group_counts.get("Overestimation", 0)),
            "test_xai0_n": int(xai_counts.get(0, 0)),
            "test_xai1_n": int(xai_counts.get(1, 0)),
            "both_treatment_arms": bool(len(treatment_counts) == 2),
            "all_calibration_groups": bool(all(group_counts.get(group, 0) > 0 for group in CALIBRATION_ORDER)),
            "both_xai_conditions": bool(len(xai_counts) == 2),
            "train_test_disjoint": bool(len(set(train_index).intersection(set(test_index))) == 0),
        })
    return rows


def run_test(test_id: str, description: str, function: Callable[[], None]) -> Dict[str, Any]:
    try:
        function()
        return {"test_id": test_id, "description": description, "status": "PASS", "error": ""}
    except Exception as exc:
        return {"test_id": test_id, "description": description, "status": "FAIL", "error": repr(exc)}


def g04_unit_tests(frame: pd.DataFrame, fold_rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    tests: List[Dict[str, Any]] = []

    def equal(actual: Any, expected: Any) -> None:
        if actual != expected:
            raise AssertionError("%r != %r" % (actual, expected))

    tests.append(run_test("G04-T01", "Analytic sample contains 249 aggregate rows", lambda: equal(len(frame), 249)))
    tests.append(run_test("G04-T02", "Treatment coding is raw tutorial=0 -> assigned tutorial", lambda: equal(frame.groupby("tutorial_raw")["treatment"].first().to_dict(), {0: 1, 1: 0})))
    tests.append(run_test("G04-T03", "Observed treatment counts are 124 tutorial and 125 no tutorial", lambda: equal(frame["treatment"].value_counts().to_dict(), {0: 125, 1: 124})))
    tests.append(run_test("G04-T04", "Calibration group counts match the frozen audit", lambda: equal(frame["calibration_group"].value_counts().to_dict(), {"Overestimation": 101, "Accurate": 76, "Underestimation": 72})))
    tests.append(run_test("G04-T05", "Primary feature registry passes leakage validation", lambda: validate_feature_registry(PRIMARY_FEATURES)))
    tests.append(run_test("G04-T06", "Sensitivity feature registry passes leakage validation", lambda: validate_feature_registry(SENSITIVITY_FEATURES)))
    tests.append(run_test("G04-T07", "Extension frame contains no participant identifier columns", lambda: equal(bool({"username", "user_id", "ai_id"}.intersection(frame.columns)), False)))
    tests.append(run_test("G04-T08", "Fixed policy coverage matches the registered matrix", lambda: equal(policy_coverage(frame), EXPECTED_POLICY_COVERAGE)))

    assignments = policy_assignments(frame)
    tests.append(run_test("G04-T09", "P01 and P06 are complements", lambda: equal(bool(np.all(assignments["P01"] + assignments["P06"] == 1)), True)))
    tests.append(run_test("G04-T10", "P02 and P05 are complements", lambda: equal(bool(np.all(assignments["P02"] + assignments["P05"] == 1)), True)))
    tests.append(run_test("G04-T11", "P03 and P04 are complements", lambda: equal(bool(np.all(assignments["P03"] + assignments["P04"] == 1)), True)))

    tests.append(run_test("G04-T12", "O01 equals absolute first miscalibration minus absolute second miscalibration", lambda: equal(bool(np.allclose(frame[OUTCOME_COLUMNS["O01"]], frame["miscalibration_first"].abs() - frame["miscalibration_second"].abs())), True)))
    tests.append(run_test("G04-T13", "O05 uses fixed six-task denominator", lambda: equal(bool(np.allclose(frame[OUTCOME_COLUMNS["O05"]], frame["second_negative_ai_reliance"] / 6.0)), True)))
    tests.append(run_test("G04-T14", "O06 uses fixed six-task denominator", lambda: equal(bool(np.allclose(frame[OUTCOME_COLUMNS["O06"]], frame["second_negative_self_reliance"] / 6.0)), True)))
    tests.append(run_test("G04-T15", "Bounded outcomes remain in [0,1]", lambda: equal(bool(all(frame[column].dropna().between(0, 1).all() for column in [OUTCOME_COLUMNS[key] for key in ("O03", "O04", "O05", "O06", "O07", "O08", "O09", "O10")])), True)))
    tests.append(run_test("G04-T16", "Defined-ratio missingness preserves known second-batch denominator counts", lambda: equal({"rair": int(frame[DEFINED_RATIO_OUTCOMES["O09"]].isna().sum()), "rsr": int(frame[DEFINED_RATIO_OUTCOMES["O10"]].isna().sum())}, {"rair": 17, "rsr": 103})))

    def fold_invariants() -> None:
        equal(len(fold_rows), 100)
        if not all(bool(row["both_treatment_arms"]) for row in fold_rows):
            raise AssertionError("At least one test fold lacks both treatment arms")
        if not all(bool(row["all_calibration_groups"]) for row in fold_rows):
            raise AssertionError("At least one test fold lacks a calibration group")
        if not all(bool(row["both_xai_conditions"]) for row in fold_rows):
            raise AssertionError("At least one test fold lacks an XAI condition")
        if not all(bool(row["train_test_disjoint"]) for row in fold_rows):
            raise AssertionError("Train/test overlap detected")
    tests.append(run_test("G04-T17", "Repeated cross-fitting produces 100 balanced disjoint test folds", fold_invariants))

    def synthetic_estimator_test() -> None:
        n = 200
        treatment = np.tile([0, 1], n // 2)
        y = 1.0 + 2.0 * treatment
        e = np.full(n, 0.5)
        m0 = np.full(n, 1.0)
        m1 = np.full(n, 3.0)
        nobody = np.zeros(n, dtype=int)
        everybody = np.ones(n, dtype=int)
        for estimator in (
            lambda d: policy_value_or(d, m0, m1),
            lambda d: policy_value_ipw(y, treatment, d, e),
            lambda d: policy_value_aipw(y, treatment, d, e, m0, m1),
        ):
            left = estimator(everybody)
            right = estimator(nobody)
            contrast = policy_contrast(left, right)
            if not math.isclose(left.policy_value, 3.0, abs_tol=1e-12):
                raise AssertionError("All-tutorial value mismatch")
            if not math.isclose(right.policy_value, 1.0, abs_tol=1e-12):
                raise AssertionError("No-tutorial value mismatch")
            if not math.isclose(contrast.policy_value, 2.0, abs_tol=1e-12):
                raise AssertionError("Synthetic contrast mismatch")
    tests.append(run_test("G04-T18", "OR, IPW, and AIPW recover an exact synthetic policy contrast", synthetic_estimator_test))

    tests.append(run_test("G04-T19", "Propensity clipping enforces the registered numerical boundary", lambda: equal(clip_propensity([0.0, 0.5, 1.0]).tolist(), [0.025, 0.5, 0.975])))
    return tests


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    frame = build_extension_frame(repo)

    calibration_overlap = count_by(frame, ["calibration_group"])
    order_overlap = count_by(frame, ["order_id"])
    order_calibration_overlap = count_by(frame, ["order_id", "calibration_group"])
    xai_calibration_overlap = count_by(frame, ["xai_raw", "calibration_group"])
    fixed_support = policy_support_rows(frame)
    feature_overlap = feature_overlap_rows(frame)
    fold_rows = fold_audit_rows(frame)

    propensity = fit_cross_fitted_propensity(
        frame,
        numeric_features=PRIMARY_NUMERIC_FEATURES,
        categorical_features=PRIMARY_CATEGORICAL_FEATURES,
        n_splits=5,
        repeats=20,
        seed=20260827,
    )["propensity"]
    propensity_rows, propensity_summary = propensity_summary_rows(frame, propensity)

    unit_tests = g04_unit_tests(frame, fold_rows)
    test_failures = [row for row in unit_tests if row["status"] != "PASS"]

    policy_registry = [
        {
            "policy_id": policy.policy_id,
            "name": policy.name,
            "description": policy.description,
            "coverage_n": int((frame["policy_%s" % policy.policy_id] == 1).sum()),
            "coverage_fraction": float(frame["policy_%s" % policy.policy_id].mean()),
        }
        for policy in POLICIES
    ]
    feature_registry = [
        {"feature": feature, "registry": "Primary", "timing": "pre-tutorial", "leakage_check": "PASS"}
        for feature in PRIMARY_FEATURES
    ] + [
        {"feature": feature, "registry": "Sensitivity addition", "timing": "pre-tutorial", "leakage_check": "PASS"}
        for feature in SENSITIVITY_FEATURES if feature not in PRIMARY_FEATURES
    ]
    outcome_registry = outcome_registry_summary(frame)

    sparse_order_group_cells = [row for row in order_calibration_overlap if not row["both_arms_observed"]]
    all_fixed_supported = all(row["both_actual_arms_in_each_nonempty_region"] for row in fixed_support)
    all_calibration_supported = all(row["both_arms_observed"] for row in calibration_overlap)
    all_order_supported = all(row["both_arms_observed"] for row in order_overlap)
    all_xai_group_supported = all(row["both_arms_observed"] for row in xai_calibration_overlap)

    g03_passed = bool(all_fixed_supported and all_calibration_supported and all_order_supported and all_xai_group_supported)
    learned_policy_decision = (
        "Conditionally supported under regularized models and coverage/overlap gates; do not use fully saturated "
        "order-by-calibration-by-XAI interactions because some granular cells lack both observed arms."
    )
    g04_passed = len(test_failures) == 0

    g03_summary = {
        "schema_version": "1.0",
        "gate": "G03",
        "status": "PASS" if g03_passed else "FAIL",
        "sample_n": int(len(frame)),
        "tutorial_n": int((frame["treatment"] == 1).sum()),
        "no_tutorial_n": int((frame["treatment"] == 0).sum()),
        "all_fixed_policies_supported": all_fixed_supported,
        "all_calibration_groups_have_both_observed_arms": all_calibration_supported,
        "all_task_orders_have_both_observed_arms": all_order_supported,
        "all_xai_by_calibration_cells_have_both_observed_arms": all_xai_group_supported,
        "order_by_calibration_cells_without_both_arms_n": len(sparse_order_group_cells),
        "order_by_calibration_cells_without_both_arms": sparse_order_group_cells,
        "propensity_overlap": propensity_summary,
        "fixed_policy_decision": "P00-P07 are descriptively supported for associational standardization." if all_fixed_supported else "At least one fixed policy lacks observed-arm support.",
        "learned_policy_decision": learned_policy_decision,
        "causal_identification_claimed": False,
        "participant_level_data_emitted": False,
    }

    g04_summary = {
        "schema_version": "1.0",
        "gate": "G04",
        "status": "PASS" if g04_passed else "FAIL",
        "unit_tests_total": len(unit_tests),
        "unit_tests_passed": len(unit_tests) - len(test_failures),
        "unit_tests_failed": len(test_failures),
        "policy_registry_frozen": True,
        "feature_registry_frozen": True,
        "outcome_registry_frozen": True,
        "estimators_implemented": ["outcome regression", "IPW", "AIPW"],
        "repeated_cross_fitting_implemented": True,
        "source_policy_values_computed": False,
        "source_extension_results_viewed": False,
        "upstream_util_imported": False,
        "participant_level_data_emitted": False,
        "failed_tests": test_failures,
    }

    write_tsv(out / "g03_calibration_overlap.tsv", calibration_overlap)
    write_tsv(out / "g03_task_order_overlap.tsv", order_overlap)
    write_tsv(out / "g03_order_calibration_overlap.tsv", order_calibration_overlap)
    write_tsv(out / "g03_xai_calibration_overlap.tsv", xai_calibration_overlap)
    write_tsv(out / "g03_fixed_policy_support.tsv", fixed_support)
    write_tsv(out / "g03_feature_bin_overlap.tsv", feature_overlap)
    write_tsv(out / "g03_cross_fitted_propensity_summary.tsv", propensity_rows)
    write_tsv(out / "g03_fold_balance.tsv", fold_rows)
    write_json(out / "g03_summary.json", g03_summary)

    write_tsv(out / "g04_policy_registry.tsv", policy_registry)
    write_tsv(out / "g04_feature_registry.tsv", feature_registry)
    write_tsv(out / "g04_outcome_registry.tsv", outcome_registry)
    write_tsv(out / "g04_unit_tests.tsv", unit_tests)
    write_json(out / "g04_summary.json", g04_summary)

    overall = {
        "schema_version": "1.0",
        "stage": "G03 positivity and G04 implementation freeze",
        "passed": bool(g03_passed and g04_passed),
        "g03_status": g03_summary["status"],
        "g04_status": g04_summary["status"],
        "sample_n": int(len(frame)),
        "policy_values_computed": False,
        "extension_results_viewed": False,
        "causal_identification_claimed": False,
        "participant_level_data_emitted": False,
    }
    write_json(out / "g03_g04_gate_summary.json", overall)

    (out / "G03_STATUS.md").write_text(
        "# G03 Positivity Gate\n\n"
        "- Status: **%s**\n" % g03_summary["status"]
        + "- Fixed policies P00-P07: **%s**\n" % ("Supported" if all_fixed_supported else "Not fully supported")
        + "- Calibration groups with both observed arms: **%s**\n" % all_calibration_supported
        + "- Task orders with both observed arms: **%s**\n" % all_order_supported
        + "- Granular order x calibration cells without both arms: **%d**\n" % len(sparse_order_group_cells)
        + "- Learned policy: **Conditionally supported; remains blocked until G09**\n"
        + "- Causal identification claimed: **NO**\n",
        encoding="utf-8",
    )
    (out / "G04_STATUS.md").write_text(
        "# G04 Implementation and Leakage-Test Gate\n\n"
        "- Status: **%s**\n" % g04_summary["status"]
        + "- Unit tests passed: **%d/%d**\n" % (g04_summary["unit_tests_passed"], g04_summary["unit_tests_total"])
        + "- Policy values computed on source outcomes: **NO**\n"
        + "- Extension results viewed: **NO**\n"
        + "- Upstream `util.py` imported: **NO**\n"
        + "- Participant-level data emitted: **NO**\n",
        encoding="utf-8",
    )

    print(json.dumps(overall, sort_keys=True))
    return 0 if overall["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
