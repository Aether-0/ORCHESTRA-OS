#!/usr/bin/env python3
"""Focused contract tests for the standalone v2/v3/v4 CSV validator."""

from __future__ import annotations

import csv
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = REPOSITORY / "tests/integration/validate_paper_cpu_csv.py"

spec = importlib.util.spec_from_file_location("paper_cpu_csv_validator", VALIDATOR_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load validator from {VALIDATOR_PATH}")
validator = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = validator
spec.loader.exec_module(validator)


def valid_v2_row() -> dict[str, str]:
    """Return a single baseline row satisfying every historical v2 invariant."""

    return {
        "tick": "1",
        "mode": "baseline",
        "cpu_now": "0.10000000",
        "cpu_pred": "0.10000000",
        "decision_cpu": "0.10000000",
        "prediction_used": "0",
        "confidence": "1.00000000",
        "forecast_error": "0.00000000",
        "frame_age_ms": "1.00000000",
        "mem": "0.10000000",
        "thermal": "0.10000000",
        "directive": "SLEEP",
        "run": "0",
        "sleep": "4",
        "migrate": "0",
        "throttle": "0",
        "yield": "0",
        "eligible_workers": "4",
        "fallback_workers": "0",
        "S1": "1.00000000",
        "S2": "1.00000000",
        "S3": "1.00000000",
        "S4": "1.00000000",
        "Q": "1.00000000",
        "jitter_sigma": "0.02000000",
        "switch_penalty": "0.00000000",
        "consensus_blend": "0.00000000",
        "next_jitter_sigma": "0.02000000",
        "next_switch_penalty": "0.00000000",
        "next_consensus_blend": "0.00000000",
        "controller_updated": "0",
        "controller_step": "0",
        "controller_reason": "NONE",
        "controller_beta": "0.00000000",
        "jitter_saturated": "0",
        "switch_saturated": "0",
        "consensus_saturated": "0",
        "consensus_applied": "0",
        "rejected_frames": "0",
        "missed_deadlines": "0",
    }


def valid_v3_row() -> dict[str, str]:
    """Return a v3 row with four successful observable SLEEP operations."""

    row = valid_v2_row()
    row.update(
        {
            "metrics_schema": validator.SCHEMA_V3,
            "S3_global": "1.00000000",
            "S3_conditioned": "1.00000000",
            "S2_selected": "1.00000000",
            "S2_effective": "1.00000000",
            "action_attempt_count": "4",
            "effective_action_success_count": "4",
            "action_error_count": "0",
            "migration_attempt_count": "0",
            "migration_valid_requested_cpu_count": "0",
            "migration_affinity_success_count": "0",
            "migration_observed_success_count": "0",
            "migration_observed_success_fraction": "1.00000000",
            "sleep_attempt_count": "4",
            "sleep_effective_success_count": "4",
            "sleep_effectiveness_fraction": "1.00000000",
            "requested_sleep_ns_total": "140000000",
            "observed_sleep_ns_total": "150000000",
            "yield_attempt_count": "0",
            "yield_call_success_count": "0",
            "yield_call_success_fraction": "1.00000000",
            "throttle_attempt_count": "0",
            "throttle_operation_success_count": "0",
            "throttle_operation_success_fraction": "1.00000000",
            "fallback_fraction": "0.00000000",
            "fallback_reason": "NONE",
        }
    )
    return row


def valid_v4_row() -> dict[str, str]:
    """Return a first accepted no-change v4 row with neutral burst telemetry."""

    row = valid_v3_row()
    row.update(
        {
            "metrics_schema": validator.SCHEMA_V4,
            "S4_burst": "1.00000000",
            "change_fraction": "0.00000000",
            "dominant_transition_fraction": "0.00000000",
            "justified_change_fraction": "0.00000000",
            "oscillation_penalty": "0.00000000",
            "dominant_old_action": "-1",
            "dominant_new_action": "-1",
            "changed_eligible_workers": "0",
            "justified_changed_workers": "0",
            "dominant_transition_count": "0",
            "rolling_window_burst_count": "0",
            "rolling_window_oscillation_count": "0",
            "current_directive_valid": "1",
            "previous_directive_valid": "0",
            "directive_transition_valid": "0",
            "large_burst_event": "0",
            "repeated_oscillation_event": "0",
        }
    )
    return row


def valid_v4_mass_transition_row(tick: int, directive: str, old_action: int,
                                 new_action: int, rolling_bursts: int,
                                 rolling_oscillations: int) -> dict[str, str]:
    """Return an all-worker, directive-justified large transition v4 row."""

    row = valid_v4_row()
    action_values = {field: "0" for field in validator.ACTION_FIELDS}
    action_values[validator.ACTION_FIELDS[new_action]] = "4"
    oscillation_penalty = min(0.50, 0.15 * rolling_oscillations)
    # All four workers changed coherently and followed a newly valid directive.
    burst_penalty = 0.8 * 1.0 * 1.0 * (0.20 + 0.80 * 0.0)
    s4_burst = 1.0 - burst_penalty - oscillation_penalty
    row.update(
        {
            "tick": str(tick),
            "directive": directive,
            **action_values,
            "S2": "1.00000000",
            "S3": "1.00000000",
            "S4": "0.00000000",
            "Q": "0.00000000",
            "S3_global": "1.00000000",
            "S3_conditioned": "1.00000000",
            "S2_selected": "1.00000000",
            "S2_effective": "1.00000000",
            "action_attempt_count": "4",
            "effective_action_success_count": "4",
            "action_error_count": "0",
            "migration_attempt_count": "0",
            "migration_valid_requested_cpu_count": "0",
            "migration_affinity_success_count": "0",
            "migration_observed_success_count": "0",
            "migration_observed_success_fraction": "1.00000000",
            "sleep_attempt_count": "0",
            "sleep_effective_success_count": "0",
            "sleep_effectiveness_fraction": "1.00000000",
            "requested_sleep_ns_total": "0",
            "observed_sleep_ns_total": "0",
            "yield_attempt_count": "0",
            "yield_call_success_count": "0",
            "yield_call_success_fraction": "1.00000000",
            "throttle_attempt_count": "0",
            "throttle_operation_success_count": "0",
            "throttle_operation_success_fraction": "1.00000000",
            "S4_burst": f"{s4_burst:.8f}",
            "change_fraction": "1.00000000",
            "dominant_transition_fraction": "1.00000000",
            "justified_change_fraction": "1.00000000",
            "oscillation_penalty": f"{oscillation_penalty:.8f}",
            "dominant_old_action": str(old_action),
            "dominant_new_action": str(new_action),
            "changed_eligible_workers": "4",
            "justified_changed_workers": "4",
            "dominant_transition_count": "4",
            "rolling_window_burst_count": str(rolling_bursts),
            "rolling_window_oscillation_count": str(rolling_oscillations),
            "current_directive_valid": "1",
            "previous_directive_valid": "1",
            "directive_transition_valid": "1",
            "large_burst_event": "1",
            "repeated_oscillation_event": str(int(rolling_oscillations > 0)),
        }
    )
    return row


class CsvValidatorTests(unittest.TestCase):
    def write_and_validate(
        self,
        header: tuple[str, ...],
        row: dict[str, str],
        expected_schema: str | None = None,
    ) -> tuple[int, str]:
        with tempfile.TemporaryDirectory(prefix="orchestra-csv-validator-") as directory:
            path = Path(directory) / "metrics.csv"
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=header, extrasaction="ignore")
                writer.writeheader()
                writer.writerow(row)
            return validator.validate(
                path, "baseline", 1, 1, False, set(), expected_schema
            )

    def assert_v3_rejected(self, row: dict[str, str]) -> None:
        with self.assertRaises(AssertionError):
            self.write_and_validate(validator.V3_HEADER, row, validator.SCHEMA_V3)

    def assert_v4_rejected(self, row: dict[str, str]) -> None:
        with self.assertRaises(AssertionError):
            self.write_and_validate(validator.V4_HEADER, row, validator.SCHEMA_V4)

    def write_rows_and_validate(
        self,
        header: tuple[str, ...],
        rows: list[dict[str, str]],
        expected_schema: str | None = None,
    ) -> tuple[int, str]:
        with tempfile.TemporaryDirectory(prefix="orchestra-csv-validator-") as directory:
            path = Path(directory) / "metrics.csv"
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=header, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)
            return validator.validate(
                path, "baseline", len(rows), len(rows), False, set(), expected_schema
            )

    def test_valid_historical_v2_contract(self) -> None:
        rows, schema = self.write_and_validate(
            validator.V2_HEADER, valid_v2_row(), validator.SCHEMA_V2
        )
        self.assertEqual((rows, schema), (1, validator.SCHEMA_V2))

    def test_valid_v3_contract(self) -> None:
        rows, schema = self.write_and_validate(
            validator.V3_HEADER, valid_v3_row(), validator.SCHEMA_V3
        )
        self.assertEqual((rows, schema), (1, validator.SCHEMA_V3))

    def test_valid_v4_contract(self) -> None:
        rows, schema = self.write_and_validate(
            validator.V4_HEADER, valid_v4_row(), validator.SCHEMA_V4
        )
        self.assertEqual((rows, schema), (1, validator.SCHEMA_V4))

    def test_v4_validated_directive_transition_and_reversal(self) -> None:
        first = valid_v4_row()
        second = valid_v4_mass_transition_row(2, "RUN", 1, 0, 1, 0)
        third = valid_v4_mass_transition_row(3, "SLEEP", 0, 1, 2, 1)
        rows, schema = self.write_rows_and_validate(
            validator.V4_HEADER, [first, second, third], validator.SCHEMA_V4
        )
        self.assertEqual((rows, schema), (3, validator.SCHEMA_V4))

    def test_v4_nonburst_row_does_not_carry_forward_burst_count(self) -> None:
        first = valid_v4_row()
        burst = valid_v4_mass_transition_row(2, "RUN", 1, 0, 1, 0)
        steady = valid_v4_mass_transition_row(3, "RUN", 0, 0, 0, 0)
        steady.update(
            {
                "S4": "1.00000000",
                "Q": "1.00000000",
                "S4_burst": "1.00000000",
                "change_fraction": "0.00000000",
                "dominant_transition_fraction": "0.00000000",
                "justified_change_fraction": "0.00000000",
                "oscillation_penalty": "0.00000000",
                "dominant_old_action": "-1",
                "dominant_new_action": "-1",
                "changed_eligible_workers": "0",
                "justified_changed_workers": "0",
                "dominant_transition_count": "0",
                "rolling_window_burst_count": "0",
                "rolling_window_oscillation_count": "0",
                "previous_directive_valid": "1",
                "directive_transition_valid": "0",
                "large_burst_event": "0",
                "repeated_oscillation_event": "0",
            }
        )
        rows, schema = self.write_rows_and_validate(
            validator.V4_HEADER, [first, burst, steady], validator.SCHEMA_V4
        )
        self.assertEqual((rows, schema), (3, validator.SCHEMA_V4))

    def test_v4_single_change_is_not_a_population_burst(self) -> None:
        row = valid_v4_row()
        row.update(
            {
                "S4": "0.75000000",
                "Q": f"{0.75 ** 0.25:.8f}",
                "S4_burst": "1.00000000",
                "change_fraction": "0.25000000",
                "dominant_transition_fraction": "1.00000000",
                "dominant_old_action": "0",
                "dominant_new_action": "1",
                "changed_eligible_workers": "1",
                "dominant_transition_count": "1",
            }
        )
        rows, schema = self.write_and_validate(
            validator.V4_HEADER, row, validator.SCHEMA_V4
        )
        self.assertEqual((rows, schema), (1, validator.SCHEMA_V4))

    def test_v4_zero_eligible_workers_are_neutral_and_unjustified(self) -> None:
        row = valid_v4_row()
        row.update(
            {
                "run": "0",
                "sleep": "0",
                "eligible_workers": "0",
                "fallback_workers": "0",
                "S2": "1.00000000",
                "S3": "1.00000000",
                "S4": "1.00000000",
                "Q": "1.00000000",
                "S2_selected": "1.00000000",
                "S2_effective": "1.00000000",
                "action_attempt_count": "0",
                "effective_action_success_count": "0",
                "sleep_attempt_count": "0",
                "sleep_effective_success_count": "0",
                "requested_sleep_ns_total": "0",
                "observed_sleep_ns_total": "0",
                "current_directive_valid": "0",
                "previous_directive_valid": "0",
            }
        )
        rows, schema = self.write_and_validate(
            validator.V4_HEADER, row, validator.SCHEMA_V4
        )
        self.assertEqual((rows, schema), (1, validator.SCHEMA_V4))

    def test_v3_row_falsely_labeled_v2_is_rejected(self) -> None:
        row = valid_v3_row()
        row["metrics_schema"] = validator.SCHEMA_V2
        self.assert_v3_rejected(row)

    def test_v2_row_cannot_be_falsely_labeled_v3(self) -> None:
        row = valid_v2_row()
        row["metrics_schema"] = validator.SCHEMA_V3
        malformed_header = validator.V2_HEADER + ("metrics_schema",)
        with self.assertRaises(AssertionError):
            self.write_and_validate(malformed_header, row, validator.SCHEMA_V3)

    def test_fatal_action_error_cannot_also_be_effective(self) -> None:
        row = valid_v3_row()
        row["action_error_count"] = "1"
        self.assert_v3_rejected(row)

    def test_migration_success_requires_valid_requested_cpu(self) -> None:
        row = valid_v3_row()
        row.update(
            {
                "migration_attempt_count": "1",
                "migration_valid_requested_cpu_count": "0",
                "migration_affinity_success_count": "1",
                "migration_observed_success_count": "1",
                "migration_observed_success_fraction": "1.00000000",
            }
        )
        self.assert_v3_rejected(row)

    def test_effective_compliance_cannot_exceed_one(self) -> None:
        row = valid_v3_row()
        row["S2_effective"] = "1.00000001"
        self.assert_v3_rejected(row)

    def test_negative_observed_sleep_is_rejected(self) -> None:
        row = valid_v3_row()
        row["observed_sleep_ns_total"] = "-1"
        self.assert_v3_rejected(row)

    def test_bounded_sleep_aggregate_is_rejected_above_schema_limit(self) -> None:
        row = valid_v3_row()
        row["requested_sleep_ns_total"] = "32000000001"
        self.assert_v3_rejected(row)

    def test_nonfinite_telemetry_is_rejected(self) -> None:
        row = valid_v3_row()
        row["S2_effective"] = "nan"
        self.assert_v3_rejected(row)

    def test_unknown_fallback_reason_is_rejected(self) -> None:
        row = valid_v3_row()
        row["fallback_reason"] = "UNBOUNDED_STRING"
        self.assert_v3_rejected(row)

    def test_truncated_v3_row_is_rejected(self) -> None:
        row = valid_v3_row()
        with tempfile.TemporaryDirectory(prefix="orchestra-csv-validator-") as directory:
            path = Path(directory) / "truncated.csv"
            with path.open("w", encoding="utf-8", newline="") as stream:
                stream.write(",".join(validator.V3_HEADER) + "\n")
                stream.write(",".join(row[field] for field in validator.V3_HEADER[:-1]) + "\n")
            with self.assertRaises(AssertionError):
                validator.validate(path, "baseline", 1, 1, False, set(), validator.SCHEMA_V3)

    def test_inconsistent_action_totals_are_rejected(self) -> None:
        row = valid_v3_row()
        row["sleep"] = "3"
        self.assert_v3_rejected(row)

    def test_effective_successes_cannot_exceed_attempts(self) -> None:
        row = valid_v3_row()
        row["effective_action_success_count"] = "5"
        self.assert_v3_rejected(row)

    def test_zero_denominator_policy_is_explicit(self) -> None:
        row = valid_v3_row()
        row.update(
            {
                "run": "0",
                "sleep": "0",
                "eligible_workers": "0",
                "S2": "1.00000000",
                "S3": "1.00000000",
                "S4": "1.00000000",
                "Q": "1.00000000",
                "S2_selected": "1.00000000",
                "S2_effective": "1.00000000",
                "action_attempt_count": "0",
                "effective_action_success_count": "0",
                "sleep_attempt_count": "0",
                "sleep_effective_success_count": "0",
                "requested_sleep_ns_total": "0",
                "observed_sleep_ns_total": "0",
                "fallback_workers": "0",
                "fallback_fraction": "0.00000000",
                "fallback_reason": "NONE",
            }
        )
        rows, schema = self.write_and_validate(
            validator.V3_HEADER, row, validator.SCHEMA_V3
        )
        self.assertEqual((rows, schema), (1, validator.SCHEMA_V3))

    def test_v4_s4_burst_cannot_be_negative(self) -> None:
        row = valid_v4_row()
        row["S4_burst"] = "-0.00000001"
        self.assert_v4_rejected(row)

    def test_v4_s4_burst_cannot_exceed_one(self) -> None:
        row = valid_v4_row()
        row["S4_burst"] = "1.00000001"
        self.assert_v4_rejected(row)

    def test_v4_changed_count_cannot_exceed_eligible(self) -> None:
        row = valid_v4_row()
        row["changed_eligible_workers"] = "5"
        self.assert_v4_rejected(row)

    def test_v4_justified_count_cannot_exceed_changed(self) -> None:
        row = valid_v4_row()
        row.update(
            {
                "changed_eligible_workers": "1",
                "justified_changed_workers": "2",
                "dominant_transition_count": "1",
                "dominant_old_action": "0",
                "dominant_new_action": "1",
                "change_fraction": "0.25000000",
                "dominant_transition_fraction": "1.00000000",
                "justified_change_fraction": "2.00000000",
            }
        )
        self.assert_v4_rejected(row)

    def test_v4_dominant_count_cannot_exceed_changed(self) -> None:
        row = valid_v4_row()
        row.update(
            {
                "changed_eligible_workers": "1",
                "dominant_transition_count": "2",
                "dominant_old_action": "0",
                "dominant_new_action": "1",
                "change_fraction": "0.25000000",
                "dominant_transition_fraction": "2.00000000",
            }
        )
        self.assert_v4_rejected(row)

    def test_v4_invalid_dominant_action_enum_is_rejected(self) -> None:
        row = valid_v4_row()
        row.update(
            {
                "changed_eligible_workers": "1",
                "dominant_transition_count": "1",
                "dominant_old_action": "5",
                "dominant_new_action": "1",
                "change_fraction": "0.25000000",
                "dominant_transition_fraction": "1.00000000",
            }
        )
        self.assert_v4_rejected(row)

    def test_v4_nonfinite_oscillation_penalty_is_rejected(self) -> None:
        row = valid_v4_row()
        row["oscillation_penalty"] = "nan"
        self.assert_v4_rejected(row)

    def test_v4_no_changes_require_zero_dominant_transition(self) -> None:
        row = valid_v4_row()
        row["dominant_transition_count"] = "1"
        self.assert_v4_rejected(row)

    def test_v4_no_change_row_cannot_report_a_burst_window(self) -> None:
        row = valid_v4_row()
        row["rolling_window_burst_count"] = "1"
        self.assert_v4_rejected(row)

    def test_v4_rejected_frame_cannot_mark_transition_justified(self) -> None:
        first = valid_v4_row()
        second = valid_v4_mass_transition_row(2, "RUN", 1, 0, 1, 0)
        second["rejected_frames"] = "1"
        with self.assertRaises(AssertionError):
            self.write_rows_and_validate(
                validator.V4_HEADER, [first, second], validator.SCHEMA_V4
            )

    def test_v4_stale_or_invalid_frame_cannot_mark_transition_justified(self) -> None:
        row = valid_v4_row()
        row.update(
            {
                "S4": "0.75000000",
                "Q": f"{0.75 ** 0.25:.8f}",
                "change_fraction": "0.25000000",
                "dominant_transition_fraction": "1.00000000",
                "justified_change_fraction": "1.00000000",
                "dominant_old_action": "0",
                "dominant_new_action": "1",
                "changed_eligible_workers": "1",
                "dominant_transition_count": "1",
                "current_directive_valid": "0",
                "previous_directive_valid": "0",
                "directive_transition_valid": "1",
                "justified_changed_workers": "1",
            }
        )
        self.assert_v4_rejected(row)

    def test_truncated_v4_row_is_rejected(self) -> None:
        row = valid_v4_row()
        with tempfile.TemporaryDirectory(prefix="orchestra-csv-validator-") as directory:
            path = Path(directory) / "truncated-v4.csv"
            with path.open("w", encoding="utf-8", newline="") as stream:
                stream.write(",".join(validator.V4_HEADER) + "\n")
                stream.write(",".join(row[field] for field in validator.V4_HEADER[:-1]) + "\n")
            with self.assertRaises(AssertionError):
                validator.validate(path, "baseline", 1, 1, False, set(), validator.SCHEMA_V4)

    def test_v3_row_falsely_labeled_v4_is_rejected(self) -> None:
        row = valid_v3_row()
        row["metrics_schema"] = validator.SCHEMA_V4
        with self.assertRaises(AssertionError):
            self.write_and_validate(validator.V3_HEADER, row, validator.SCHEMA_V4)

    def test_v4_row_falsely_labeled_v3_is_rejected(self) -> None:
        row = valid_v4_row()
        row["metrics_schema"] = validator.SCHEMA_V3
        with self.assertRaises(AssertionError):
            self.write_and_validate(validator.V4_HEADER, row, validator.SCHEMA_V3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
