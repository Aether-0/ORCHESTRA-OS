#!/usr/bin/env python3
"""Strictly validate historical v2 and append-only v3/v4 paper-CPU CSV files.

The v2 contract predates an inline schema cell, so it is recognized only by
its exact historical 40-column header.  v3 and v4 are recognized by their
exact append-only headers *and* require the explicit ``metrics_schema`` value
in every row.  Callers can additionally pin the expected schema with
``--schema``; benchmark manifests should do so.  The v4 burst metric remains
experimental and deliberately does not alter historical S4 or Q validation.
"""

from __future__ import annotations

import argparse
import csv
import math
import re
from pathlib import Path
from typing import Final


SCHEMA_V2: Final = "orchestra.paper_cpu.metrics/v2"
SCHEMA_V3: Final = "orchestra.paper_cpu.metrics/v3"
SCHEMA_V4: Final = "orchestra.paper_cpu.metrics/v4"
SCHEMA_V5: Final = "orchestra.paper_cpu.metrics/v5"
SCHEMA_V6: Final = "orchestra.paper_cpu.metrics/v6"

# This is the immutable historical v2 order.  Do not append v3 fields here.
V2_HEADER: Final = (
    "tick",
    "mode",
    "cpu_now",
    "cpu_pred",
    "decision_cpu",
    "prediction_used",
    "confidence",
    "forecast_error",
    "frame_age_ms",
    "mem",
    "thermal",
    "directive",
    "run",
    "sleep",
    "migrate",
    "throttle",
    "yield",
    "eligible_workers",
    "fallback_workers",
    "S1",
    "S2",
    "S3",
    "S4",
    "Q",
    "jitter_sigma",
    "switch_penalty",
    "consensus_blend",
    "next_jitter_sigma",
    "next_switch_penalty",
    "next_consensus_blend",
    "controller_updated",
    "controller_step",
    "controller_reason",
    "controller_beta",
    "jitter_saturated",
    "switch_saturated",
    "consensus_saturated",
    "consensus_applied",
    "rejected_frames",
    "missed_deadlines",
)

# v3 is strictly append-only relative to V2_HEADER.  The telemetry fields are
# aggregate observation-window data, not claims about Linux kernel dispatch.
V3_APPEND: Final = (
    "metrics_schema",
    "S3_global",
    "S3_conditioned",
    "S2_selected",
    "S2_effective",
    "action_attempt_count",
    "effective_action_success_count",
    "action_error_count",
    "migration_attempt_count",
    "migration_valid_requested_cpu_count",
    "migration_affinity_success_count",
    "migration_observed_success_count",
    "migration_observed_success_fraction",
    "sleep_attempt_count",
    "sleep_effective_success_count",
    "sleep_effectiveness_fraction",
    "requested_sleep_ns_total",
    "observed_sleep_ns_total",
    "yield_attempt_count",
    "yield_call_success_count",
    "yield_call_success_fraction",
    "throttle_attempt_count",
    "throttle_operation_success_count",
    "throttle_operation_success_fraction",
    "fallback_fraction",
    "fallback_reason",
)
V3_HEADER: Final = V2_HEADER + V3_APPEND

# v4 is strictly append-only relative to the immutable 66-column v3
# contract.  Its action identifiers use the canonical action enum 0..4 and
# reserve -1/-1 for the no-change diagnostic only.
V4_APPEND: Final = (
    "S4_burst",
    "change_fraction",
    "dominant_transition_fraction",
    "justified_change_fraction",
    "oscillation_penalty",
    "dominant_old_action",
    "dominant_new_action",
    "changed_eligible_workers",
    "justified_changed_workers",
    "dominant_transition_count",
    "rolling_window_burst_count",
    "rolling_window_oscillation_count",
    "current_directive_valid",
    "previous_directive_valid",
    "directive_transition_valid",
    "large_burst_event",
    "repeated_oscillation_event",
)
V4_HEADER: Final = V3_HEADER + V4_APPEND

V5_APPEND: Final = (
    "controller_state",
    "previous_state",
    "transition_reason",
    "state_residence_time",
    "valid_control_history_count",
    "invalid_frame_fault_count",
    "saturation_bitmask",
    "saturation_direction",
    "saturation_persistence",
    "oscillation_score",
    "oscillation_event",
    "rollback_event",
    "rollback_reason",
    "recovery_progress",
    "last_known_good_available",
    "requested_jitter",
    "applied_jitter",
    "requested_switch",
    "applied_switch",
    "requested_consensus",
    "applied_consensus",
    "update_accepted",
    "update_suppressed",
    "suppression_reason",
)
V5_HEADER: Final = V4_HEADER + V5_APPEND

V6_APPEND: Final = (
    "policy_mode", "policy_schema_version", "policy_generation",
    "policy_update_allowed", "policy_update_applied",
    "policy_update_suppression_reason", "policy_exploration_enabled",
    "policy_train_update_count", "policy_adapt_update_count",
    "policy_load_status", "policy_save_status",
    "policy_digest_prefix", "policy_format_version"
)
V6_HEADER: Final = V5_HEADER + V6_APPEND

ACTIONS: Final = ("RUN", "SLEEP", "MIGRATE", "THROTTLE", "YIELD")
ACTION_FIELDS: Final = ("run", "sleep", "migrate", "throttle", "yield")
ACTION_IDS: Final = tuple(range(len(ACTIONS)))
NO_DOMINANT_ACTION: Final = -1
MODES: Final = ("baseline", "orchestra")
CONTROLLER_REASONS: Final = ("NONE", "S3", "S4", "S3+S4")
FALLBACK_REASONS: Final = (
    "NONE",
    "NO_VALID_FRAME",
    "LAST_KNOWN_GOOD_EXPIRED",
    "MULTIPLE",
)

COMMON_NORMALIZED: Final = (
    "cpu_now",
    "cpu_pred",
    "decision_cpu",
    "confidence",
    "forecast_error",
    "mem",
    "thermal",
    "S1",
    "S2",
    "S3",
    "S4",
    "Q",
)
V3_NORMALIZED: Final = (
    "S3_global",
    "S3_conditioned",
    "S2_selected",
    "S2_effective",
    "migration_observed_success_fraction",
    "sleep_effectiveness_fraction",
    "yield_call_success_fraction",
    "throttle_operation_success_fraction",
    "fallback_fraction",
)
V4_NORMALIZED: Final = (
    "S4_burst",
    "change_fraction",
    "dominant_transition_fraction",
    "justified_change_fraction",
    "oscillation_penalty",
)
BOOLEAN_FIELDS: Final = (
    "prediction_used",
    "controller_updated",
    "jitter_saturated",
    "switch_saturated",
    "consensus_saturated",
    "consensus_applied",
)
ACTUATOR_BOUNDS: Final = {
    "jitter_sigma": (0.0, 0.20),
    "switch_penalty": (0.0, 0.30),
    "consensus_blend": (0.0, 0.15),
    "next_jitter_sigma": (0.0, 0.20),
    "next_switch_penalty": (0.0, 0.30),
    "next_consensus_blend": (0.0, 0.15),
}
V3_COUNT_FIELDS: Final = (
    "action_attempt_count",
    "effective_action_success_count",
    "action_error_count",
    "migration_attempt_count",
    "migration_valid_requested_cpu_count",
    "migration_affinity_success_count",
    "migration_observed_success_count",
    "sleep_attempt_count",
    "sleep_effective_success_count",
    "requested_sleep_ns_total",
    "observed_sleep_ns_total",
    "yield_attempt_count",
    "yield_call_success_count",
    "throttle_attempt_count",
    "throttle_operation_success_count",
)
V3_WORKER_COUNT_FIELDS: Final = tuple(
    field
    for field in V3_COUNT_FIELDS
    if field not in {"requested_sleep_ns_total", "observed_sleep_ns_total"}
)
V4_COUNT_FIELDS: Final = (
    "changed_eligible_workers",
    "justified_changed_workers",
    "dominant_transition_count",
    "rolling_window_burst_count",
    "rolling_window_oscillation_count",
)
V4_BOOLEAN_FIELDS: Final = (
    "current_directive_valid",
    "previous_directive_valid",
    "directive_transition_valid",
    "large_burst_event",
    "repeated_oscillation_event",
)
MAX_WORKERS: Final = 64
# 64 workers × 500 ms bounded request; observed sleep permits 250 ms oversleep.
MAX_REQUESTED_SLEEP_NS_TOTAL: Final = 32_000_000_000
MAX_OBSERVED_SLEEP_NS_TOTAL: Final = 48_000_000_000
BURST_HISTORY_SEQUENCE_WINDOW: Final = 4
BURST_HISTORY_CAPACITY: Final = 8
MAX_ROLLING_BURST_COUNT: Final = BURST_HISTORY_SEQUENCE_WINDOW + 1
MAX_ROLLING_OSCILLATION_COUNT: Final = BURST_HISTORY_SEQUENCE_WINDOW
OSCILLATION_PENALTY_WEIGHT: Final = 0.15
MAX_OSCILLATION_PENALTY: Final = 0.50


def close(left: float, right: float, tolerance: float = 1e-7) -> bool:
    """Compare CSV-rounded metric values using the documented Q tolerance."""

    return math.isclose(left, right, rel_tol=tolerance, abs_tol=tolerance)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--mode", choices=MODES, required=True)
    parser.add_argument(
        "--schema",
        choices=(SCHEMA_V2, SCHEMA_V3, SCHEMA_V4, SCHEMA_V5, SCHEMA_V6),
        help="pin the expected metrics schema; v3/v4/v5/v6 benchmark invocations must pin it",
    )
    parser.add_argument("--min-rows", type=int, default=1)
    parser.add_argument("--max-rows", type=int)
    parser.add_argument("--expect-rejections", action="store_true")
    parser.add_argument(
        "--expect-controller-skip", type=int, action="append", default=[]
    )
    return parser.parse_args()


from typing import Sequence, Optional, Final


def _schema_from_header(fieldnames: Sequence[str] | None) -> str:
    header = tuple(fieldnames or ())
    if header == V2_HEADER:
        return SCHEMA_V2
    if header == V3_HEADER:
        return SCHEMA_V3
    if header == V4_HEADER:
        return SCHEMA_V4
    if header == V5_HEADER:
        return SCHEMA_V5
    if header == V6_HEADER:
        return SCHEMA_V6
    raise AssertionError(
        "unexpected CSV header; expected exact historical v2 or append-only v3/v4/v5/v6 "
        f"contract, got {list(header)!r}"
    )


def _raw_uint(row: dict[str, str | None], field: str, tick: int) -> int:
    text = row.get(field)
    if text is None or re.fullmatch(r"[0-9]+", text) is None:
        raise AssertionError(
            f"tick {tick}: {field} must be an unsigned decimal integer"
        )
    return int(text, 10)


def _raw_int(row: dict[str, str | None], field: str, tick: int) -> int:
    """Parse a strictly decimal signed integer used by a versioned enum."""

    text = row.get(field)
    if text is None or re.fullmatch(r"-?(?:0|[1-9][0-9]*)", text) is None:
        raise AssertionError(f"tick {tick}: {field} must be a decimal integer")
    return int(text, 10)


def _raw_float(
    row: dict[str, str | None],
    field: str,
    tick: int,
    lower: float | None = None,
    upper: float | None = None,
) -> float:
    text = row.get(field)
    if text is None or text == "":
        raise AssertionError(f"tick {tick}: {field} is missing")
    try:
        value = float(text)
    except ValueError as exc:
        raise AssertionError(f"tick {tick}: {field} is not numeric") from exc
    if not math.isfinite(value):
        raise AssertionError(f"tick {tick}: {field} must be finite")
    if lower is not None and value < lower:
        raise AssertionError(f"tick {tick}: {field} below {lower}: {value}")
    if upper is not None and value > upper:
        raise AssertionError(f"tick {tick}: {field} above {upper}: {value}")
    return value


def _fraction(numerator: int, denominator: int, empty_value: float) -> float:
    """Return a versioned fraction with an explicit empty-population value."""

    return empty_value if denominator == 0 else numerator / denominator


def _validate_common_row(
    row: dict[str, str | None],
    tick: int,
    mode: str,
    schema: str,
    expected_controller_skips: set[int],
    controller_step: int,
) -> tuple[int, int, int]:
    """Validate shared v2/v3/v4 fields and return chronology counters."""

    if row.get("mode") != mode:
        raise AssertionError(f"tick {tick}: mode {row.get('mode')!r} != {mode!r}")
    directive = row.get("directive")
    if directive not in ACTIONS:
        raise AssertionError(f"tick {tick}: invalid directive {directive!r}")

    for field in COMMON_NORMALIZED:
        _raw_float(row, field, tick, 0.0, 1.0)
    for field in BOOLEAN_FIELDS:
        value = _raw_uint(row, field, tick)
        if value not in (0, 1):
            raise AssertionError(f"tick {tick}: {field} is not boolean")
    for field, (lower, upper) in ACTUATOR_BOUNDS.items():
        _raw_float(row, field, tick, lower, upper)
    _raw_float(row, "frame_age_ms", tick, 0.0)
    _raw_float(row, "controller_beta", tick, 0.0, 0.02)

    eligible = _raw_uint(row, "eligible_workers", tick)
    if eligible > MAX_WORKERS:
        raise AssertionError(f"tick {tick}: eligible workers exceed {MAX_WORKERS}")
    action_counts = [_raw_uint(row, field, tick) for field in ACTION_FIELDS]
    if any(count > MAX_WORKERS for count in action_counts):
        raise AssertionError(f"tick {tick}: action count exceeds {MAX_WORKERS}")
    actions = sum(action_counts)
    if actions != eligible:
        raise AssertionError(
            f"tick {tick}: action count {actions} != eligible {eligible}"
        )
    fallbacks = _raw_uint(row, "fallback_workers", tick)
    if fallbacks > MAX_WORKERS or fallbacks > eligible:
        raise AssertionError(f"tick {tick}: invalid fallback count {fallbacks}")

    directive_index = ACTIONS.index(directive)
    expected_s2 = _fraction(action_counts[directive_index], eligible, 1.0)
    if not close(_raw_float(row, "S2", tick, 0.0, 1.0), expected_s2):
        raise AssertionError(
            f"tick {tick}: S2 does not match selected action/directive agreement"
        )

    if eligible <= 1:
        expected_s3 = 1.0
    else:
        entropy = 0.0
        for count in action_counts:
            if count:
                probability = count / eligible
                entropy -= probability * math.log(probability)
        expected_s3 = 1.0 - entropy / math.log(len(ACTION_FIELDS))
    if not close(_raw_float(row, "S3", tick, 0.0, 1.0), expected_s3):
        raise AssertionError(f"tick {tick}: S3 action-entropy coherence mismatch")

    factors = [
        _raw_float(row, field, tick, 0.0, 1.0) for field in ("S1", "S2", "S3", "S4")
    ]
    expected_q = (
        0.0 if any(value == 0.0 for value in factors) else math.prod(factors) ** 0.25
    )
    if not close(_raw_float(row, "Q", tick, 0.0, 1.0), expected_q):
        raise AssertionError(f"tick {tick}: Q does not equal historical geometric mean")

    updated = _raw_uint(row, "controller_updated", tick)
    scheduled_update = mode == "orchestra" and tick % 20 == 0
    expected_updated = int(scheduled_update and tick not in expected_controller_skips)
    if updated != expected_updated:
        raise AssertionError(f"tick {tick}: controller cadence mismatch")
    if expected_updated:
        controller_step += 1
    if _raw_uint(row, "controller_step", tick) != controller_step:
        raise AssertionError(f"tick {tick}: controller step mismatch")
    reason = row.get("controller_reason")
    beta = _raw_float(row, "controller_beta", tick, 0.0, 0.02)
    if updated:
        if reason not in CONTROLLER_REASONS:
            raise AssertionError(f"tick {tick}: invalid controller reason {reason!r}")
        expected_beta = 0.02 / math.sqrt(1.0 + controller_step)
        if not close(beta, expected_beta):
            raise AssertionError(f"tick {tick}: controller beta mismatch")
    else:
        if reason != "NONE" or beta != 0.0:
            raise AssertionError(
                f"tick {tick}: non-update controller telemetry is nonzero"
            )
        for current, nxt in (
            ("jitter_sigma", "next_jitter_sigma"),
            ("switch_penalty", "next_switch_penalty"),
            ("consensus_blend", "next_consensus_blend"),
        ):
            if not close(_raw_float(row, current, tick), _raw_float(row, nxt, tick)):
                raise AssertionError(f"tick {tick}: {nxt} changed off cadence")

    if mode == "baseline":
        if _raw_uint(row, "prediction_used", tick) != 0:
            raise AssertionError(f"tick {tick}: baseline used a prediction")
        if not close(
            _raw_float(row, "decision_cpu", tick), _raw_float(row, "cpu_now", tick)
        ):
            raise AssertionError(f"tick {tick}: baseline did not use observed CPU")
        if (
            _raw_float(row, "forecast_error", tick) != 0.0
            or _raw_float(row, "confidence", tick) != 1.0
        ):
            raise AssertionError(
                f"tick {tick}: baseline fidelity reference is not normalized"
            )
        if _raw_float(row, "S2", tick) != 1.0:
            raise AssertionError(f"tick {tick}: reactive baseline was noncompliant")

    # v2 has no inline identifier; later versions are explicitly self-identifying.
    if schema in (SCHEMA_V3, SCHEMA_V4) and row.get("metrics_schema") != schema:
        raise AssertionError(
            f"tick {tick}: metrics_schema {row.get('metrics_schema')!r} != {schema!r}"
        )
    return eligible, fallbacks, controller_step


def _validate_v3_row(
    row: dict[str, str | None], tick: int, eligible: int, fallbacks: int
) -> None:
    """Validate v3 append-only telemetry and reconstructable identities."""

    for field in V3_NORMALIZED:
        _raw_float(row, field, tick, 0.0, 1.0)
    if not close(_raw_float(row, "S3_global", tick), _raw_float(row, "S3", tick)):
        raise AssertionError(f"tick {tick}: historical S3 is not S3_global")
    if not close(_raw_float(row, "S2_selected", tick), _raw_float(row, "S2", tick)):
        raise AssertionError(f"tick {tick}: historical S2 is not S2_selected")

    counts = {field: _raw_uint(row, field, tick) for field in V3_COUNT_FIELDS}
    if any(counts[field] > MAX_WORKERS for field in V3_WORKER_COUNT_FIELDS):
        raise AssertionError(f"tick {tick}: v3 worker count exceeds {MAX_WORKERS}")
    if counts["requested_sleep_ns_total"] > MAX_REQUESTED_SLEEP_NS_TOTAL:
        raise AssertionError(
            f"tick {tick}: requested sleep exceeds bounded telemetry maximum"
        )
    if counts["observed_sleep_ns_total"] > MAX_OBSERVED_SLEEP_NS_TOTAL:
        raise AssertionError(
            f"tick {tick}: observed sleep exceeds bounded telemetry maximum"
        )
    action_attempts = counts["action_attempt_count"]
    effective_successes = counts["effective_action_success_count"]
    action_errors = counts["action_error_count"]
    if action_attempts > eligible:
        raise AssertionError(f"tick {tick}: action attempts exceed eligible workers")
    if effective_successes > action_attempts:
        raise AssertionError(f"tick {tick}: effective successes exceed action attempts")
    if action_errors > action_attempts:
        raise AssertionError(f"tick {tick}: action errors exceed action attempts")
    if effective_successes + action_errors > action_attempts:
        raise AssertionError(
            f"tick {tick}: an action attempt cannot be both effective and fatally erroneous"
        )

    # An action-specific attempt is a subset of all observable attempted actions.
    action_specific_attempts = (
        counts["migration_attempt_count"]
        + counts["sleep_attempt_count"]
        + counts["yield_attempt_count"]
        + counts["throttle_attempt_count"]
    )
    if action_specific_attempts > action_attempts:
        raise AssertionError(
            f"tick {tick}: action-specific attempts exceed action attempts"
        )
    selected_limits = {
        "migration_attempt_count": _raw_uint(row, "migrate", tick),
        "sleep_attempt_count": _raw_uint(row, "sleep", tick),
        "yield_attempt_count": _raw_uint(row, "yield", tick),
        "throttle_attempt_count": _raw_uint(row, "throttle", tick),
    }
    for field, selected in selected_limits.items():
        if counts[field] > selected:
            raise AssertionError(f"tick {tick}: {field} exceeds selected action count")

    migration_attempts = counts["migration_attempt_count"]
    migration_valid = counts["migration_valid_requested_cpu_count"]
    migration_affinity = counts["migration_affinity_success_count"]
    migration_observed = counts["migration_observed_success_count"]
    if not (
        migration_observed
        <= migration_affinity
        <= migration_valid
        <= migration_attempts
    ):
        raise AssertionError(
            f"tick {tick}: migration outcome requires observed <= affinity <= valid CPU <= attempts"
        )
    expected_migration_fraction = _fraction(migration_observed, migration_attempts, 1.0)
    if not close(
        _raw_float(row, "migration_observed_success_fraction", tick),
        expected_migration_fraction,
    ):
        raise AssertionError(f"tick {tick}: migration effectiveness fraction mismatch")

    sleep_attempts = counts["sleep_attempt_count"]
    sleep_successes = counts["sleep_effective_success_count"]
    if sleep_successes > sleep_attempts:
        raise AssertionError(f"tick {tick}: sleep successes exceed sleep attempts")
    expected_sleep_fraction = _fraction(sleep_successes, sleep_attempts, 1.0)
    if not close(
        _raw_float(row, "sleep_effectiveness_fraction", tick), expected_sleep_fraction
    ):
        raise AssertionError(f"tick {tick}: sleep effectiveness fraction mismatch")

    yield_attempts = counts["yield_attempt_count"]
    yield_successes = counts["yield_call_success_count"]
    if yield_successes > yield_attempts:
        raise AssertionError(f"tick {tick}: yield successes exceed yield attempts")
    expected_yield_fraction = _fraction(yield_successes, yield_attempts, 1.0)
    if not close(
        _raw_float(row, "yield_call_success_fraction", tick), expected_yield_fraction
    ):
        raise AssertionError(f"tick {tick}: yield call success fraction mismatch")

    throttle_attempts = counts["throttle_attempt_count"]
    throttle_successes = counts["throttle_operation_success_count"]
    if throttle_successes > throttle_attempts:
        raise AssertionError(
            f"tick {tick}: throttle successes exceed throttle attempts"
        )
    expected_throttle_fraction = _fraction(throttle_successes, throttle_attempts, 1.0)
    if not close(
        _raw_float(row, "throttle_operation_success_fraction", tick),
        expected_throttle_fraction,
    ):
        raise AssertionError(
            f"tick {tick}: throttle operation success fraction mismatch"
        )

    expected_s2_effective = _fraction(effective_successes, eligible, 1.0)
    if not close(_raw_float(row, "S2_effective", tick), expected_s2_effective):
        raise AssertionError(f"tick {tick}: S2_effective outcome fraction mismatch")

    expected_fallback_fraction = _fraction(fallbacks, eligible, 0.0)
    if not close(
        _raw_float(row, "fallback_fraction", tick), expected_fallback_fraction
    ):
        raise AssertionError(f"tick {tick}: fallback fraction mismatch")
    fallback_reason = row.get("fallback_reason")
    if fallback_reason not in FALLBACK_REASONS:
        raise AssertionError(
            f"tick {tick}: unknown fallback reason {fallback_reason!r}"
        )
    if fallbacks == 0 and fallback_reason != "NONE":
        raise AssertionError(f"tick {tick}: fallback reason without a fallback worker")
    if fallbacks > 0 and fallback_reason == "NONE":
        raise AssertionError(f"tick {tick}: fallback workers require a fallback reason")


def _validate_v4_row(
    row: dict[str, str | None],
    tick: int,
    eligible: int,
    last_valid_directive: str | None,
    accepted_large_bursts: list[tuple[int, int, int]],
    previous_rejections: int,
) -> str | None:
    """Validate experimental burst telemetry without changing historical S4/Q.

    The canonical userspace publisher sets frame sequence to the CSV tick, so
    the validator can independently reconstruct the fixed sequence-distance
    window from earlier accepted large-burst rows.  Only rows with a current
    accepted directive enter that bounded history; a rejected or stale row
    may describe an observed action burst, but cannot justify it or update the
    directive/history tracker.
    """

    for field in V4_NORMALIZED:
        _raw_float(row, field, tick, 0.0, 1.0)
    counts = {field: _raw_uint(row, field, tick) for field in V4_COUNT_FIELDS}
    for field in V4_BOOLEAN_FIELDS:
        value = _raw_uint(row, field, tick)
        if value not in (0, 1):
            raise AssertionError(f"tick {tick}: {field} is not boolean")

    changed = counts["changed_eligible_workers"]
    justified = counts["justified_changed_workers"]
    dominant_count = counts["dominant_transition_count"]
    rolling_bursts = counts["rolling_window_burst_count"]
    rolling_oscillations = counts["rolling_window_oscillation_count"]
    if changed > eligible:
        raise AssertionError(f"tick {tick}: changed workers exceed eligible workers")
    if justified > changed:
        raise AssertionError(f"tick {tick}: justified changes exceed changed workers")
    if dominant_count > changed:
        raise AssertionError(f"tick {tick}: dominant transition count exceeds changes")
    if rolling_bursts > MAX_ROLLING_BURST_COUNT:
        raise AssertionError(f"tick {tick}: rolling burst count exceeds bounded window")
    if rolling_oscillations > MAX_ROLLING_OSCILLATION_COUNT:
        raise AssertionError(
            f"tick {tick}: rolling oscillation count exceeds bounded window"
        )
    if rolling_oscillations > rolling_bursts:
        raise AssertionError(f"tick {tick}: rolling oscillations exceed rolling bursts")

    expected_change_fraction = _fraction(changed, eligible, 0.0)
    expected_dominant_fraction = _fraction(dominant_count, changed, 0.0)
    expected_justified_fraction = _fraction(justified, changed, 0.0)
    if not close(_raw_float(row, "change_fraction", tick), expected_change_fraction):
        raise AssertionError(f"tick {tick}: change fraction mismatch")
    if not close(
        _raw_float(row, "dominant_transition_fraction", tick),
        expected_dominant_fraction,
    ):
        raise AssertionError(f"tick {tick}: dominant transition fraction mismatch")
    if not close(
        _raw_float(row, "justified_change_fraction", tick), expected_justified_fraction
    ):
        raise AssertionError(f"tick {tick}: justified change fraction mismatch")

    dominant_old = _raw_int(row, "dominant_old_action", tick)
    dominant_new = _raw_int(row, "dominant_new_action", tick)
    if changed == 0:
        if (
            dominant_old != NO_DOMINANT_ACTION
            or dominant_new != NO_DOMINANT_ACTION
            or dominant_count != 0
        ):
            raise AssertionError(
                f"tick {tick}: no-change row must use -1/-1 and zero dominant count"
            )
    else:
        if dominant_count == 0:
            raise AssertionError(f"tick {tick}: changes require a dominant transition")
        if dominant_old not in ACTION_IDS or dominant_new not in ACTION_IDS:
            raise AssertionError(f"tick {tick}: invalid dominant action enum")
        if dominant_old == dominant_new:
            raise AssertionError(
                f"tick {tick}: dominant transition cannot retain the action"
            )
        selected_new_count = _raw_uint(row, ACTION_FIELDS[dominant_new], tick)
        if dominant_count > selected_new_count:
            raise AssertionError(
                f"tick {tick}: dominant transition exceeds selected new-action count"
            )

    current_valid = _raw_uint(row, "current_directive_valid", tick)
    previous_valid = _raw_uint(row, "previous_directive_valid", tick)
    transition_valid = _raw_uint(row, "directive_transition_valid", tick)
    if current_valid and eligible == 0:
        raise AssertionError(
            f"tick {tick}: zero eligible workers cannot accept a directive"
        )
    expected_previous_valid = int(last_valid_directive is not None)
    if previous_valid != expected_previous_valid:
        raise AssertionError(
            f"tick {tick}: previous directive validity does not match accepted-frame tracker"
        )
    expected_transition_valid = int(
        bool(
            current_valid
            and previous_valid
            and last_valid_directive is not None
            and row.get("directive") != last_valid_directive
        )
    )
    if transition_valid != expected_transition_valid:
        raise AssertionError(f"tick {tick}: directive transition validity mismatch")
    if justified and not transition_valid:
        raise AssertionError(
            f"tick {tick}: unjustified row claims directive justification"
        )
    if justified > _raw_uint(row, ACTION_FIELDS[ACTIONS.index(row["directive"])], tick):
        raise AssertionError(
            f"tick {tick}: justified changes exceed selected directive actions"
        )
    rejections = _raw_uint(row, "rejected_frames", tick)
    if rejections > previous_rejections and (
        current_valid or transition_valid or justified
    ):
        raise AssertionError(
            f"tick {tick}: rejected frame cannot be valid or justify an action transition"
        )

    expected_historical_s4 = 1.0 - expected_change_fraction
    if not close(_raw_float(row, "S4", tick), expected_historical_s4):
        raise AssertionError(
            f"tick {tick}: historical S4 does not match changed-worker fraction"
        )

    large_burst = _raw_uint(row, "large_burst_event", tick)
    expected_large_burst = int(
        eligible > 1
        and changed > 1
        and changed * 2 >= eligible
        and changed > 0
        and dominant_count * 4 >= changed * 3
    )
    if large_burst != expected_large_burst:
        raise AssertionError(f"tick {tick}: large-burst event threshold mismatch")

    prior_large_bursts = [
        entry
        for entry in accepted_large_bursts
        if tick - entry[0] <= BURST_HISTORY_SEQUENCE_WINDOW
    ]
    # The diagnostic is event-scoped: a non-large current row reports zero,
    # rather than carrying a historical event count into a no-burst row.
    expected_rolling_bursts = len(prior_large_bursts) + 1 if large_burst else 0
    if rolling_bursts != expected_rolling_bursts:
        raise AssertionError(f"tick {tick}: rolling burst diagnostic mismatch")
    reverse_count = 0
    if large_burst:
        reverse_count = sum(
            int(old_action == dominant_new and new_action == dominant_old)
            for _, old_action, new_action in prior_large_bursts
        )
    if rolling_oscillations != reverse_count:
        raise AssertionError(f"tick {tick}: rolling oscillation diagnostic mismatch")
    expected_repeated = int(bool(large_burst and reverse_count > 0))
    if _raw_uint(row, "repeated_oscillation_event", tick) != expected_repeated:
        raise AssertionError(f"tick {tick}: repeated-oscillation event mismatch")
    expected_oscillation_penalty = min(
        MAX_OSCILLATION_PENALTY,
        OSCILLATION_PENALTY_WEIGHT * rolling_oscillations,
    )
    if not close(
        _raw_float(row, "oscillation_penalty", tick), expected_oscillation_penalty
    ):
        raise AssertionError(f"tick {tick}: oscillation penalty mismatch")

    population_scale = (
        (changed - 1) / (eligible - 1) if eligible > 1 and changed > 1 else 0.0
    )
    burst_penalty = (
        0.8
        * expected_change_fraction
        * population_scale
        * expected_dominant_fraction
        * (0.20 + 0.80 * (1.0 - expected_justified_fraction))
    )
    expected_s4_burst = max(
        0.0, min(1.0, 1.0 - burst_penalty - expected_oscillation_penalty)
    )
    if not close(_raw_float(row, "S4_burst", tick), expected_s4_burst):
        raise AssertionError(f"tick {tick}: S4_burst formula mismatch")

    if current_valid:
        if large_burst:
            accepted_large_bursts.append((tick, dominant_old, dominant_new))
        last_valid_directive = row["directive"]
    return last_valid_directive


def validate(
    path: Path,
    mode: str,
    min_rows: int,
    max_rows: int | None,
    expect_rejections: bool,
    expected_controller_skips: set[int],
    expected_schema: str | None = None,
) -> tuple[int, str]:
    """Validate one bounded invocation and return its row count and schema ID."""

    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        schema = _schema_from_header(reader.fieldnames)
        if expected_schema is not None and schema != expected_schema:
            raise AssertionError(
                f"CSV schema {schema!r} does not match expected {expected_schema!r}"
            )
        rows = list(reader)

    if len(rows) < min_rows:
        raise AssertionError(f"only {len(rows)} rows, expected at least {min_rows}")
    if max_rows is not None and len(rows) > max_rows:
        raise AssertionError(f"{len(rows)} rows, expected at most {max_rows}")

    previous_rejections = 0
    previous_missed = 0
    controller_step = 0
    last_valid_directive: str | None = None
    accepted_large_bursts: list[tuple[int, int, int]] = []
    for expected_tick, row in enumerate(rows, start=1):
        if None in row or any(value is None for value in row.values()):
            raise AssertionError(f"row {expected_tick + 1}: malformed field count")
        tick = _raw_uint(row, "tick", expected_tick)
        if tick != expected_tick:
            raise AssertionError(
                f"tick {tick}: expected sequential tick {expected_tick}"
            )
        eligible, fallbacks, controller_step = _validate_common_row(
            row, tick, mode, schema, expected_controller_skips, controller_step
        )
        if schema in (SCHEMA_V3, SCHEMA_V4):
            _validate_v3_row(row, tick, eligible, fallbacks)
        if schema == SCHEMA_V4:
            last_valid_directive = _validate_v4_row(
                row,
                tick,
                eligible,
                last_valid_directive,
                accepted_large_bursts,
                previous_rejections,
            )

        rejections = _raw_uint(row, "rejected_frames", tick)
        missed = _raw_uint(row, "missed_deadlines", tick)
        if rejections < previous_rejections or missed < previous_missed:
            raise AssertionError(f"tick {tick}: cumulative counter regressed")
        previous_rejections = rejections
        previous_missed = missed

    if expect_rejections and previous_rejections == 0:
        raise AssertionError("tamper run reported no reader rejection")
    observed_ticks = {index for index in range(1, len(rows) + 1)}
    missing_skips = expected_controller_skips - observed_ticks
    if missing_skips:
        raise AssertionError(f"expected controller skip ticks absent: {missing_skips}")
    return len(rows), schema


def main() -> int:
    args = parse_args()
    if args.min_rows < 0:
        raise AssertionError("min-rows must not be negative")
    if args.max_rows is not None and args.max_rows < args.min_rows:
        raise AssertionError("max-rows must be at least min-rows")
    skip_ticks = set(args.expect_controller_skip)
    if args.mode != "orchestra" and skip_ticks:
        raise AssertionError("controller skips are valid only in orchestra mode")
    if any(tick <= 0 or tick % 20 != 0 for tick in skip_ticks):
        raise AssertionError("controller skip ticks must be positive multiples of 20")
    rows, schema = validate(
        args.csv_path,
        args.mode,
        args.min_rows,
        args.max_rows,
        args.expect_rejections,
        skip_ticks,
        args.schema,
    )
    print(f"PASS csv={args.csv_path} rows={rows} mode={args.mode} schema={schema}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
