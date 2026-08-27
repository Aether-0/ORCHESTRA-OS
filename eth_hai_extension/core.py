"""Registered calibration-aware extension core.

This module defines only pre-tutorial features, post-tutorial outcomes, and the
transparent fixed policy class P00-P07. It imports the independently rebuilt
``eth_hai_clean.core`` and never imports the released upstream ``util.py``.

The source study does not document randomized condition assignment. All policy
quantities constructed from these data are therefore retrospective associational
standardizations, not identified causal effects.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Sequence, Tuple

import numpy as np
import pandas as pd

from eth_hai_clean.core import build_clean_metric_frame

TUTORIAL_RAW_ASSIGNED = 0
TUTORIAL_RAW_NOT_ASSIGNED = 1

CALIBRATION_ORDER: Tuple[str, ...] = (
    "Underestimation",
    "Accurate",
    "Overestimation",
)

PRIMARY_NUMERIC_FEATURES: Tuple[str, ...] = (
    "first_correct_count",
    "self_first",
    "miscalibration_first",
    "abs_miscalibration_first",
    "first_agreement_fraction",
    "first_positive_ai_reliance",
    "first_negative_self_reliance",
    "first_positive_self_reliance",
    "first_negative_ai_reliance",
    "ati",
    "propensity",
    "trust_first",
)

PRIMARY_CATEGORICAL_FEATURES: Tuple[str, ...] = (
    "calibration_group",
    "order_id",
    "xai_raw",
)

SENSITIVITY_NUMERIC_FEATURES: Tuple[str, ...] = (
    "first_switch_fraction",
    "first_appropriate_reliance",
)

PRIMARY_FEATURES: Tuple[str, ...] = PRIMARY_NUMERIC_FEATURES + PRIMARY_CATEGORICAL_FEATURES
SENSITIVITY_FEATURES: Tuple[str, ...] = PRIMARY_FEATURES + SENSITIVITY_NUMERIC_FEATURES

PROHIBITED_FEATURE_TOKENS: Tuple[str, ...] = (
    "second_",
    "overall_",
    "self_second",
    "miscalibration_second",
    "trust_second",
    "change_",
    "outcome_",
    "policy_value",
)

OUTCOME_COLUMNS: Dict[str, str] = {
    "O01": "outcome_abs_calibration_improvement",
    "O02": "outcome_second_abs_miscalibration",
    "O03": "outcome_second_accuracy",
    "O04": "outcome_second_accuracy_wid",
    "O05": "outcome_overreliance_harm_per_task",
    "O06": "outcome_underreliance_harm_per_task",
    "O07": "outcome_second_agreement_fraction",
    "O08": "outcome_second_switch_fraction",
    "O09": "outcome_second_rair_zero",
    "O10": "outcome_second_rsr_zero",
}

DEFINED_RATIO_OUTCOMES: Dict[str, str] = {
    "O09": "outcome_second_rair_defined",
    "O10": "outcome_second_rsr_defined",
}


@dataclass(frozen=True)
class PolicySpec:
    policy_id: str
    name: str
    description: str
    assignment: Callable[[pd.DataFrame], pd.Series]


def calibration_label(value: float) -> str:
    value = float(value)
    if value < 0:
        return "Underestimation"
    if value > 0:
        return "Overestimation"
    return "Accurate"


def treatment_from_raw(raw_tutorial: pd.Series) -> pd.Series:
    raw = pd.to_numeric(raw_tutorial, errors="raise").astype(int)
    unknown = sorted(set(raw.unique()) - {TUTORIAL_RAW_ASSIGNED, TUTORIAL_RAW_NOT_ASSIGNED})
    if unknown:
        raise ValueError("Unknown tutorial raw coding: %r" % unknown)
    return (1 - raw).astype(int)


def _policy_all(frame: pd.DataFrame, value: int) -> pd.Series:
    return pd.Series(np.full(len(frame), int(value), dtype=int), index=frame.index)


def _group_mask(frame: pd.DataFrame, groups: Iterable[str]) -> pd.Series:
    allowed = set(groups)
    return frame["calibration_group"].isin(allowed).astype(int)


POLICIES: Tuple[PolicySpec, ...] = (
    PolicySpec("P00", "No tutorial", "Assign tutorial to nobody", lambda f: _policy_all(f, 0)),
    PolicySpec("P01", "Underestimators only", "Assign when first calibration gap < 0", lambda f: _group_mask(f, {"Underestimation"})),
    PolicySpec("P02", "Accurate only", "Assign when first calibration gap = 0", lambda f: _group_mask(f, {"Accurate"})),
    PolicySpec("P03", "Overestimators only", "Assign when first calibration gap > 0", lambda f: _group_mask(f, {"Overestimation"})),
    PolicySpec("P04", "Under + accurate", "Assign when first calibration gap <= 0", lambda f: _group_mask(f, {"Underestimation", "Accurate"})),
    PolicySpec("P05", "All miscalibrated", "Assign when absolute first calibration gap >= 1", lambda f: _group_mask(f, {"Underestimation", "Overestimation"})),
    PolicySpec("P06", "Accurate + over", "Assign when first calibration gap >= 0", lambda f: _group_mask(f, {"Accurate", "Overestimation"})),
    PolicySpec("P07", "Universal tutorial", "Assign tutorial to everybody", lambda f: _policy_all(f, 1)),
)

POLICY_BY_ID: Dict[str, PolicySpec] = {policy.policy_id: policy for policy in POLICIES}


def validate_feature_registry(features: Sequence[str]) -> None:
    if len(features) != len(set(features)):
        raise ValueError("Feature registry contains duplicates")
    for feature in features:
        lower = str(feature).lower()
        for token in PROHIBITED_FEATURE_TOKENS:
            if token in lower:
                raise ValueError("Post-treatment or outcome leakage feature: %s" % feature)


def policy_assignments(frame: pd.DataFrame) -> pd.DataFrame:
    assignments: Dict[str, pd.Series] = {}
    for policy in POLICIES:
        values = policy.assignment(frame).astype(int)
        if not set(values.unique()).issubset({0, 1}):
            raise ValueError("Policy %s produced non-binary assignments" % policy.policy_id)
        assignments[policy.policy_id] = values
    return pd.DataFrame(assignments, index=frame.index)


def build_extension_frame(repo: Path) -> pd.DataFrame:
    """Build the registered extension frame without participant identifiers."""
    zero = build_clean_metric_frame(repo, undefined_ratio="zero").reset_index(drop=True)
    defined = build_clean_metric_frame(repo, undefined_ratio="nan").reset_index(drop=True)
    if len(zero) != len(defined):
        raise AssertionError("Zero and defined metric frames differ in length")

    frame = zero.copy()
    frame["treatment"] = treatment_from_raw(frame["tutorial_raw"])
    frame["calibration_group"] = frame["miscalibration_first"].map(calibration_label)
    frame["abs_miscalibration_first"] = frame["miscalibration_first"].abs().astype(float)
    frame["abs_miscalibration_second"] = frame["miscalibration_second"].abs().astype(float)

    frame[OUTCOME_COLUMNS["O01"]] = frame["abs_miscalibration_first"] - frame["abs_miscalibration_second"]
    frame[OUTCOME_COLUMNS["O02"]] = frame["abs_miscalibration_second"]
    frame[OUTCOME_COLUMNS["O03"]] = frame["second_accuracy"].astype(float)
    frame[OUTCOME_COLUMNS["O04"]] = frame["second_appropriate_reliance"].astype(float)
    frame[OUTCOME_COLUMNS["O05"]] = frame["second_negative_ai_reliance"].astype(float) / 6.0
    frame[OUTCOME_COLUMNS["O06"]] = frame["second_negative_self_reliance"].astype(float) / 6.0
    frame[OUTCOME_COLUMNS["O07"]] = frame["second_agreement_fraction"].astype(float)
    frame[OUTCOME_COLUMNS["O08"]] = frame["second_switch_fraction"].astype(float)
    frame[OUTCOME_COLUMNS["O09"]] = frame["second_rair"].astype(float)
    frame[OUTCOME_COLUMNS["O10"]] = frame["second_rsr"].astype(float)
    frame[DEFINED_RATIO_OUTCOMES["O09"]] = pd.to_numeric(defined["second_rair"], errors="coerce")
    frame[DEFINED_RATIO_OUTCOMES["O10"]] = pd.to_numeric(defined["second_rsr"], errors="coerce")

    validate_feature_registry(PRIMARY_FEATURES)
    validate_feature_registry(SENSITIVITY_FEATURES)
    missing = sorted(set(SENSITIVITY_FEATURES) - set(frame.columns))
    if missing:
        raise KeyError("Registered extension features are missing: %r" % missing)

    assignments = policy_assignments(frame)
    for policy_id in assignments.columns:
        frame["policy_%s" % policy_id] = assignments[policy_id]

    forbidden_source_columns = {"username", "user_id", "ai_id"}
    if forbidden_source_columns.intersection(frame.columns):
        raise AssertionError("Participant identifiers leaked into extension frame")
    return frame


def policy_coverage(frame: pd.DataFrame) -> Dict[str, int]:
    assignments = policy_assignments(frame)
    return {policy_id: int(assignments[policy_id].sum()) for policy_id in assignments.columns}


def outcome_registry_summary(frame: pd.DataFrame) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for outcome_id, column in OUTCOME_COLUMNS.items():
        values = pd.to_numeric(frame[column], errors="coerce")
        rows.append({
            "outcome_id": outcome_id,
            "column": column,
            "n_total": int(len(values)),
            "n_defined": int(values.notna().sum()),
            "n_missing": int(values.isna().sum()),
            "minimum": float(values.min()) if values.notna().any() else None,
            "maximum": float(values.max()) if values.notna().any() else None,
            "mean": float(values.mean()) if values.notna().any() else None,
        })
    for outcome_id, column in DEFINED_RATIO_OUTCOMES.items():
        values = pd.to_numeric(frame[column], errors="coerce")
        rows.append({
            "outcome_id": outcome_id + "_defined",
            "column": column,
            "n_total": int(len(values)),
            "n_defined": int(values.notna().sum()),
            "n_missing": int(values.isna().sum()),
            "minimum": float(values.min()) if values.notna().any() else None,
            "maximum": float(values.max()) if values.notna().any() else None,
            "mean": float(values.mean()) if values.notna().any() else None,
        })
    return rows
