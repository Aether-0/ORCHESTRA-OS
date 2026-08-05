#!/usr/bin/env python3
"""Focused contract tests for the bounded signal-publication runner."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[2]
RUNNER_PATH = REPOSITORY / "tools/benchmark/run_signal_publication_microbenchmark.py"

spec = importlib.util.spec_from_file_location("orchestra_publication_microbenchmark", RUNNER_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load microbenchmark runner from {RUNNER_PATH}")
runner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runner
spec.loader.exec_module(runner)


def valid_measurement(mode: str = "generation_stamped") -> dict[str, object]:
    """Return one strict, finite completed measurement fixture."""

    return {
        "schema_id": runner.MICROBENCH_SCHEMA_ID,
        "publication_mode": mode,
        "readers": 2,
        "requested_iterations": 100,
        "warmup_iterations": 0,
        "seed": 17,
        "reader_threads_ready": 2,
        "completed": True,
        "clock_failed": False,
        "publisher_deadline_exhausted": False,
        "publisher_attempts": 100,
        "publisher_successes": 100,
        "publisher_contended": 0,
        "publisher_generation_exhausted": 0,
        "publisher_latency_sum_ns": 1000,
        "publisher_latency_max_ns": 10,
        "publisher_elapsed_ns": 1000,
        "publisher_diagnostic_attempts": 100,
        "publisher_diagnostic_publications": 100,
        "publisher_diagnostic_contention": 0,
        "publisher_diagnostic_generation_exhaustions": 0,
        "reader_snapshot_copy_attempts": 4,
        "reader_snapshot_copy_successes": 4,
        "reader_snapshot_copy_empty": 0,
        "reader_snapshot_copy_unstable": 0,
        "reader_snapshot_copy_latency_sum_ns": 40,
        "reader_snapshot_copy_latency_max_ns": 10,
        "reader_api_calls": 4,
        "reader_valid_reads": 4,
        "reader_no_new_reads": 0,
        "reader_unstable_reads": 0,
        "reader_invalid_reads": 0,
        "reader_api_latency_sum_ns": 80,
        "reader_api_latency_max_ns": 20,
        "reader_verified_frame_latency_sum_ns": 80,
        "reader_verified_frame_latency_max_ns": 20,
        "reader_elapsed_sum_ns": 80,
        "reader_elapsed_max_ns": 40,
        "reader_deadline_exits": 0,
        "reader_diagnostic_attempts": 4,
        "reader_diagnostic_verified_reads": 4,
        "reader_diagnostic_retries": 0,
        "reader_diagnostic_retry_exhaustions": 0,
        "reader_diagnostic_unstable_slots": 0,
        "reader_diagnostic_hmac_failures": 0,
        "reader_diagnostic_invalid_fields": 0,
        "reader_diagnostic_invalid_schema": 0,
        "reader_diagnostic_invalid_tier": 0,
        "reader_diagnostic_invalid_source": 0,
        "reader_diagnostic_invalid_directive": 0,
        "reader_diagnostic_invalid_sequence": 0,
        "reader_diagnostic_stale_frames": 0,
        "reader_diagnostic_invalid_key_epochs": 0,
    }


class SignalPublicationMicrobenchmarkRunnerTests(unittest.TestCase):
    def test_bounded_reader_counts_include_requested_levels_when_available(self) -> None:
        self.assertEqual(runner.bounded_reader_counts(1, 8), (1,))
        self.assertEqual(runner.bounded_reader_counts(2, 8), (1, 2))
        self.assertEqual(runner.bounded_reader_counts(4, 8), (1, 2, 4))
        self.assertEqual(runner.bounded_reader_counts(32, 8), (1, 2, 4, 8))
        self.assertEqual(runner.bounded_reader_counts(32, 16), (1, 2, 4, 16))

    def test_completed_generation_measurement_has_strict_accounting(self) -> None:
        measurement = valid_measurement()
        self.assertEqual(
            runner.validate_measurement(measurement, "generation_stamped", 2, 100, 17),
            [],
        )
        summary = runner.make_invocation_summary(measurement)
        self.assertEqual(set(summary), set(runner.INVOCATION_DERIVED_METRIC_NAMES))
        self.assertEqual(len(summary), len(runner.INVOCATION_DERIVED_METRIC_NAMES))

    def test_invalid_result_requires_exact_rejection_reason_accounting(self) -> None:
        measurement = valid_measurement("legacy")
        measurement.update(
            {
                "reader_valid_reads": 3,
                "reader_invalid_reads": 1,
                "reader_verified_frame_latency_sum_ns": 60,
                "reader_diagnostic_verified_reads": 3,
                "reader_diagnostic_invalid_schema": 1,
            }
        )
        self.assertEqual(runner.validate_measurement(measurement, "legacy", 2, 100, 17), [])
        measurement["reader_invalid_reads"] = 0
        issues = runner.validate_measurement(measurement, "legacy", 2, 100, 17)
        self.assertTrue(any("per-reason rejection diagnostics" in issue for issue in issues))

    def test_generation_rejection_is_not_accepted_as_a_completed_measurement(self) -> None:
        measurement = valid_measurement()
        measurement.update(
            {
                "reader_valid_reads": 3,
                "reader_invalid_reads": 1,
                "reader_verified_frame_latency_sum_ns": 60,
                "reader_diagnostic_verified_reads": 3,
                "reader_diagnostic_invalid_schema": 1,
            }
        )
        issues = runner.validate_measurement(measurement, "generation_stamped", 2, 100, 17)
        self.assertTrue(any("generation-stamped reader" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main(verbosity=2)
