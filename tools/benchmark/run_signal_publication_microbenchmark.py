#!/usr/bin/env python3
"""Run bounded ORCHESTRA signal-publication microbenchmark variants.

The resulting data measures authenticated userspace publication/read API costs
under controlled local thread contention.  It does not establish Linux
scheduler behavior, end-to-end ORCHESTRA performance, or a causal scheduling
improvement.  Only Python's standard library is used.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import resource
import shlex
import shutil
import signal
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, TypeAlias


MICROBENCH_SCHEMA_ID: Final = "orchestra.signal_publication.microbenchmark/v1"
PUBLICATION_MODES: Final = ("legacy", "generation_stamped")
MODE_MACROS: Final = {"legacy": "1", "generation_stamped": "0"}
CLAIM_LIMITATION: Final = (
    "This isolated userspace microbenchmark measures bounded authenticated signal "
    "publication/read API behavior only. It does not prove kernel scheduler behavior, "
    "end-to-end ORCHESTRA performance, or a causal scheduling improvement."
)
COMPARISON_DESIGN: Final = "descriptive-unpaired-microbenchmark"
MAX_RUNNER_READERS: Final = 16
INTERNAL_JOIN_BUDGET_MS: Final = 2_000
INVOCATION_DERIVED_METRIC_NAMES: Final[tuple[str, ...]] = (
    "publisher_attempts_per_sec",
    "publisher_successes_per_sec",
    "publisher_mean_latency_ns",
    "publisher_max_latency_ns",
    "publisher_success_fraction",
    "publisher_contention_fraction",
    "publisher_contention_count",
    "publisher_generation_exhaustion_count",
    "reader_api_calls_per_aggregate_thread_sec",
    "reader_valid_reads_per_aggregate_thread_sec",
    "reader_api_mean_latency_ns",
    "reader_api_max_latency_ns",
    "reader_snapshot_copy_success_fraction",
    "reader_snapshot_copy_empty_fraction",
    "reader_snapshot_copy_unstable_fraction",
    "reader_snapshot_copy_mean_latency_ns",
    "reader_snapshot_copy_max_latency_ns",
    "reader_verified_frame_mean_latency_ns",
    "reader_verified_frame_max_latency_ns",
    "reader_valid_fraction",
    "reader_retry_fraction",
    "reader_unstable_fraction",
    "reader_retry_exhaustion_count",
    "reader_unstable_slot_observation_count",
    "reader_invalid_frame_count",
    "reader_hmac_failure_count",
    "reader_invalid_fields_count",
    "reader_invalid_schema_count",
    "reader_invalid_tier_count",
    "reader_invalid_source_count",
    "reader_invalid_directive_count",
    "reader_invalid_sequence_count",
    "reader_stale_frame_count",
    "reader_invalid_key_epoch_count",
)

if len(INVOCATION_DERIVED_METRIC_NAMES) != len(set(INVOCATION_DERIVED_METRIC_NAMES)):
    raise RuntimeError("microbenchmark derived metric names must be unique")

Scalar: TypeAlias = int | float | str | bool | None
JsonObject: TypeAlias = dict[str, object]


class MicrobenchmarkError(RuntimeError):
    """Raised when bounded measurement setup is invalid or unsafe."""


@dataclass(frozen=True)
class ProcessResult:
    """Result of one externally bounded microbenchmark invocation."""

    return_code: int | None
    timed_out: bool
    interrupted: bool
    utc_start: str
    utc_end: str
    wall_duration_sec: float
    user_cpu_sec: float
    system_cpu_sec: float


def utc_now() -> str:
    """Return a UTC timestamp with an explicit ``Z`` suffix."""

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    """Hash a regular file in bounded memory."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    """Write deterministic JSON while rejecting non-finite values."""

    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def resolve_regular_file(path: Path, label: str, executable: bool = False) -> Path:
    """Resolve and validate one input file without silently falling back."""

    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise MicrobenchmarkError(f"{label} is not a regular file: {resolved}")
    if executable and not os.access(resolved, os.X_OK):
        raise MicrobenchmarkError(f"{label} is not executable: {resolved}")
    return resolved


def available_processor_count() -> int:
    """Return the processor count available to this process on the host."""

    try:
        available = len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        available = os.cpu_count() or 1
    return max(1, available)


def bounded_reader_counts(host_processors: int, configured_maximum: int) -> tuple[int, ...]:
    """Return 1, 2, 4, and the explicit host-bounded maximum when available."""

    host_maximum = min(host_processors, configured_maximum, MAX_RUNNER_READERS)
    if host_maximum < 1:
        raise MicrobenchmarkError("no processor is available for a reader thread")
    return tuple(sorted({count for count in (1, 2, 4, host_maximum) if count <= host_maximum}))


def finite_json(value: object) -> bool:
    """Recursively reject JSON values containing non-finite numeric values."""

    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(finite_json(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and finite_json(item) for key, item in value.items())
    return True


def read_json_measurement(path: Path) -> JsonObject:
    """Parse exactly one JSON measurement object emitted by the C harness."""

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise MicrobenchmarkError(f"cannot read microbenchmark stdout {path}: {exc}") from exc
    if not text.strip():
        raise MicrobenchmarkError("microbenchmark emitted no JSON measurement")
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise MicrobenchmarkError(f"microbenchmark stdout is not JSON: {exc}") from exc
    if not isinstance(value, dict) or not finite_json(value):
        raise MicrobenchmarkError("microbenchmark JSON must be a finite object")
    return value


def require_measurement_string(measurement: JsonObject, name: str) -> str:
    """Read a required non-empty string metric."""

    value = measurement.get(name)
    if not isinstance(value, str) or not value:
        raise MicrobenchmarkError(f"measurement field {name!r} must be a non-empty string")
    return value


def require_measurement_int(measurement: JsonObject, name: str) -> int:
    """Read a required nonnegative integer metric while rejecting booleans."""

    value = measurement.get(name)
    if type(value) is not int or value < 0:
        raise MicrobenchmarkError(f"measurement field {name!r} must be a nonnegative integer")
    return value


def require_measurement_bool(measurement: JsonObject, name: str) -> bool:
    """Read a required JSON boolean metric."""

    value = measurement.get(name)
    if type(value) is not bool:
        raise MicrobenchmarkError(f"measurement field {name!r} must be boolean")
    return value


def validate_measurement(
    measurement: JsonObject,
    mode: str,
    readers: int,
    iterations: int,
    seed: int,
) -> list[str]:
    """Validate reconstructable C-harness invariants before summary inclusion."""

    issues: list[str] = []
    try:
        if require_measurement_string(measurement, "schema_id") != MICROBENCH_SCHEMA_ID:
            issues.append("measurement schema_id does not match the strict microbenchmark contract")
        if require_measurement_string(measurement, "publication_mode") != mode:
            issues.append("measurement publication_mode does not match the compiled variant")
        if require_measurement_int(measurement, "readers") != readers:
            issues.append("measurement reader count does not match the invocation")
        if require_measurement_int(measurement, "requested_iterations") != iterations:
            issues.append("measurement requested_iterations does not match the invocation")
        if require_measurement_int(measurement, "seed") != seed:
            issues.append("measurement seed does not match the invocation")
        if require_measurement_int(measurement, "reader_threads_ready") != readers:
            issues.append("not every requested reader thread reached the start barrier")

        completed = require_measurement_bool(measurement, "completed")
        if require_measurement_bool(measurement, "clock_failed"):
            issues.append("microbenchmark reported a monotonic-clock failure")
        if require_measurement_bool(measurement, "publisher_deadline_exhausted"):
            issues.append("publisher exhausted its bounded internal deadline")

        publisher_attempts = require_measurement_int(measurement, "publisher_attempts")
        publisher_successes = require_measurement_int(measurement, "publisher_successes")
        publisher_contended = require_measurement_int(measurement, "publisher_contended")
        publisher_exhausted = require_measurement_int(
            measurement, "publisher_generation_exhausted"
        )
        if publisher_attempts > iterations:
            issues.append("publisher attempts exceed requested iterations")
        if publisher_successes + publisher_contended + publisher_exhausted != publisher_attempts:
            issues.append("publisher result counters do not sum to publisher attempts")
        if publisher_exhausted != 0:
            issues.append("publisher generation exhaustion is not a valid bounded run")
        if require_measurement_int(measurement, "publisher_diagnostic_attempts") != publisher_attempts:
            issues.append("publisher diagnostic attempts do not match result attempts")
        if require_measurement_int(measurement, "publisher_diagnostic_publications") != publisher_successes:
            issues.append("publisher diagnostic publications do not match successful results")
        if require_measurement_int(measurement, "publisher_diagnostic_contention") != publisher_contended:
            issues.append("publisher diagnostic contention does not match contended results")
        if (
            require_measurement_int(measurement, "publisher_diagnostic_generation_exhaustions")
            != publisher_exhausted
        ):
            issues.append("publisher diagnostic generation exhaustion does not match results")
        if publisher_attempts and require_measurement_int(measurement, "publisher_elapsed_ns") == 0:
            issues.append("nonempty publisher measurement has zero elapsed time")

        snapshot_attempts = require_measurement_int(
            measurement, "reader_snapshot_copy_attempts"
        )
        snapshot_successes = require_measurement_int(
            measurement, "reader_snapshot_copy_successes"
        )
        snapshot_empty = require_measurement_int(measurement, "reader_snapshot_copy_empty")
        snapshot_unstable = require_measurement_int(
            measurement, "reader_snapshot_copy_unstable"
        )
        snapshot_latency_sum = require_measurement_int(
            measurement, "reader_snapshot_copy_latency_sum_ns"
        )
        snapshot_latency_max = require_measurement_int(
            measurement, "reader_snapshot_copy_latency_max_ns"
        )
        reader_calls = require_measurement_int(measurement, "reader_api_calls")
        reader_valid = require_measurement_int(measurement, "reader_valid_reads")
        reader_no_new = require_measurement_int(measurement, "reader_no_new_reads")
        reader_unstable = require_measurement_int(measurement, "reader_unstable_reads")
        reader_invalid = require_measurement_int(measurement, "reader_invalid_reads")
        reader_api_latency_sum = require_measurement_int(
            measurement, "reader_api_latency_sum_ns"
        )
        reader_api_latency_max = require_measurement_int(
            measurement, "reader_api_latency_max_ns"
        )
        verified_latency_sum = require_measurement_int(
            measurement, "reader_verified_frame_latency_sum_ns"
        )
        verified_latency_max = require_measurement_int(
            measurement, "reader_verified_frame_latency_max_ns"
        )
        if snapshot_successes + snapshot_empty + snapshot_unstable != snapshot_attempts:
            issues.append("raw snapshot-copy result counters do not sum to attempts")
        if snapshot_attempts != reader_calls:
            issues.append("raw snapshot-copy attempts do not match complete reader API calls")
        if snapshot_successes == 0 and (snapshot_latency_sum != 0 or snapshot_latency_max != 0):
            issues.append("raw snapshot-copy latency exists without a successful snapshot")
        if snapshot_latency_max > snapshot_latency_sum:
            issues.append("raw snapshot-copy maximum latency exceeds its successful latency sum")
        if reader_valid == 0 and (verified_latency_sum != 0 or verified_latency_max != 0):
            issues.append("verified-frame latency exists without FRAME_VALID")
        if verified_latency_max > verified_latency_sum:
            issues.append("verified-frame maximum latency exceeds its successful latency sum")
        if reader_api_latency_max > reader_api_latency_sum:
            issues.append("reader API maximum latency exceeds its latency sum")
        if reader_valid + reader_no_new + reader_unstable + reader_invalid != reader_calls:
            issues.append("reader result counters do not sum to reader API calls")
        if require_measurement_int(measurement, "reader_diagnostic_attempts") != reader_calls:
            issues.append("reader diagnostic attempts do not match API calls")
        if require_measurement_int(measurement, "reader_diagnostic_verified_reads") != reader_valid:
            issues.append("reader diagnostic verified reads do not match FRAME_VALID results")
        invalid_reason_fields = (
            "reader_diagnostic_hmac_failures",
            "reader_diagnostic_invalid_fields",
            "reader_diagnostic_invalid_schema",
            "reader_diagnostic_invalid_tier",
            "reader_diagnostic_invalid_source",
            "reader_diagnostic_invalid_directive",
            "reader_diagnostic_invalid_sequence",
            "reader_diagnostic_stale_frames",
            "reader_diagnostic_invalid_key_epochs",
        )
        invalid_reason_count = sum(
            require_measurement_int(measurement, field) for field in invalid_reason_fields
        )
        if invalid_reason_count != reader_invalid:
            issues.append("invalid reader results do not match per-reason rejection diagnostics")
        if mode == "generation_stamped" and invalid_reason_count != 0:
            issues.append(
                "generation-stamped reader reported a rejected frame under valid non-tampered input"
            )
        if require_measurement_int(measurement, "reader_deadline_exits") != 0:
            issues.append("one or more readers exhausted the bounded internal deadline")
        if reader_calls and require_measurement_int(measurement, "reader_elapsed_sum_ns") == 0:
            issues.append("nonempty reader measurement has zero aggregate elapsed time")
        if not completed:
            issues.append("microbenchmark did not complete all requested publisher attempts")
        if completed and publisher_attempts != iterations:
            issues.append("completed measurement does not contain every requested attempt")
    except MicrobenchmarkError as exc:
        issues.append(str(exc))
    return issues


def safe_fraction(numerator: int, denominator: int) -> float | None:
    """Return a finite fraction or null when the metric has no denominator."""

    return numerator / denominator if denominator else None


def safe_rate(count: int, elapsed_ns: int) -> float | None:
    """Return an operation rate from monotonic nanoseconds or null."""

    return count * 1_000_000_000.0 / elapsed_ns if elapsed_ns else None


def make_invocation_summary(measurement: JsonObject) -> JsonObject:
    """Derive descriptive metrics for exactly one validated invocation."""

    publisher_attempts = require_measurement_int(measurement, "publisher_attempts")
    publisher_successes = require_measurement_int(measurement, "publisher_successes")
    publisher_contended = require_measurement_int(measurement, "publisher_contended")
    publisher_elapsed = require_measurement_int(measurement, "publisher_elapsed_ns")
    reader_calls = require_measurement_int(measurement, "reader_api_calls")
    reader_valid = require_measurement_int(measurement, "reader_valid_reads")
    reader_elapsed = require_measurement_int(measurement, "reader_elapsed_sum_ns")
    reader_retries = require_measurement_int(measurement, "reader_diagnostic_retries")
    return {
        "publisher_attempts_per_sec": safe_rate(publisher_attempts, publisher_elapsed),
        "publisher_successes_per_sec": safe_rate(publisher_successes, publisher_elapsed),
        "publisher_mean_latency_ns": safe_fraction(
            require_measurement_int(measurement, "publisher_latency_sum_ns"),
            publisher_attempts,
        ),
        "publisher_max_latency_ns": require_measurement_int(
            measurement, "publisher_latency_max_ns"
        ),
        "publisher_success_fraction": safe_fraction(publisher_successes, publisher_attempts),
        "publisher_contention_fraction": safe_fraction(publisher_contended, publisher_attempts),
        "publisher_contention_count": publisher_contended,
        "publisher_generation_exhaustion_count": require_measurement_int(
            measurement, "publisher_generation_exhausted"
        ),
        "reader_api_calls_per_aggregate_thread_sec": safe_rate(reader_calls, reader_elapsed),
        "reader_valid_reads_per_aggregate_thread_sec": safe_rate(reader_valid, reader_elapsed),
        "reader_api_mean_latency_ns": safe_fraction(
            require_measurement_int(measurement, "reader_api_latency_sum_ns"), reader_calls
        ),
        "reader_api_max_latency_ns": require_measurement_int(
            measurement, "reader_api_latency_max_ns"
        ),
        "reader_snapshot_copy_success_fraction": safe_fraction(
            require_measurement_int(measurement, "reader_snapshot_copy_successes"),
            require_measurement_int(measurement, "reader_snapshot_copy_attempts"),
        ),
        "reader_snapshot_copy_empty_fraction": safe_fraction(
            require_measurement_int(measurement, "reader_snapshot_copy_empty"),
            require_measurement_int(measurement, "reader_snapshot_copy_attempts"),
        ),
        "reader_snapshot_copy_unstable_fraction": safe_fraction(
            require_measurement_int(measurement, "reader_snapshot_copy_unstable"),
            require_measurement_int(measurement, "reader_snapshot_copy_attempts"),
        ),
        "reader_snapshot_copy_mean_latency_ns": safe_fraction(
            require_measurement_int(measurement, "reader_snapshot_copy_latency_sum_ns"),
            require_measurement_int(measurement, "reader_snapshot_copy_successes"),
        ),
        "reader_snapshot_copy_max_latency_ns": require_measurement_int(
            measurement, "reader_snapshot_copy_latency_max_ns"
        ),
        "reader_verified_frame_mean_latency_ns": safe_fraction(
            require_measurement_int(measurement, "reader_verified_frame_latency_sum_ns"),
            reader_valid,
        ),
        "reader_verified_frame_max_latency_ns": require_measurement_int(
            measurement, "reader_verified_frame_latency_max_ns"
        ),
        "reader_valid_fraction": safe_fraction(reader_valid, reader_calls),
        "reader_retry_fraction": safe_fraction(reader_retries, reader_calls),
        "reader_unstable_fraction": safe_fraction(
            require_measurement_int(measurement, "reader_unstable_reads"), reader_calls
        ),
        "reader_retry_exhaustion_count": require_measurement_int(
            measurement, "reader_diagnostic_retry_exhaustions"
        ),
        "reader_unstable_slot_observation_count": require_measurement_int(
            measurement, "reader_diagnostic_unstable_slots"
        ),
        "reader_invalid_frame_count": require_measurement_int(
            measurement, "reader_invalid_reads"
        ),
        "reader_hmac_failure_count": require_measurement_int(
            measurement, "reader_diagnostic_hmac_failures"
        ),
        "reader_invalid_fields_count": require_measurement_int(
            measurement, "reader_diagnostic_invalid_fields"
        ),
        "reader_invalid_schema_count": require_measurement_int(
            measurement, "reader_diagnostic_invalid_schema"
        ),
        "reader_invalid_tier_count": require_measurement_int(
            measurement, "reader_diagnostic_invalid_tier"
        ),
        "reader_invalid_source_count": require_measurement_int(
            measurement, "reader_diagnostic_invalid_source"
        ),
        "reader_invalid_directive_count": require_measurement_int(
            measurement, "reader_diagnostic_invalid_directive"
        ),
        "reader_invalid_sequence_count": require_measurement_int(
            measurement, "reader_diagnostic_invalid_sequence"
        ),
        "reader_stale_frame_count": require_measurement_int(
            measurement, "reader_diagnostic_stale_frames"
        ),
        "reader_invalid_key_epoch_count": require_measurement_int(
            measurement, "reader_diagnostic_invalid_key_epochs"
        ),
    }


def summarize_values(values: list[float]) -> JsonObject:
    """Summarize independent invocation values without treating rows as samples."""

    if not values:
        return {"n": 0, "mean": None, "stdev": None, "minimum": None, "maximum": None}
    mean = statistics.fmean(values)
    return {
        "n": len(values),
        "mean": mean,
        "stdev": statistics.stdev(values) if len(values) > 1 else None,
        "minimum": min(values),
        "maximum": max(values),
    }


def aggregate_summaries(summaries: list[JsonObject]) -> JsonObject:
    """Aggregate validated invocations by variant and reader-count cohort."""

    cohorts: JsonObject = {}
    for mode in PUBLICATION_MODES:
        for readers in sorted({int(summary["readers"]) for summary in summaries}):
            matching = [
                summary
                for summary in summaries
                if summary["publication_mode"] == mode and summary["readers"] == readers
            ]
            if not matching:
                continue
            metrics: JsonObject = {}
            for metric in INVOCATION_DERIVED_METRIC_NAMES:
                values = [
                    float(summary["derived_metrics"][metric])
                    for summary in matching
                    if summary["derived_metrics"][metric] is not None
                ]
                metrics[metric] = summarize_values(values)
            cohorts[f"{mode}/readers={readers}"] = {
                "publication_mode": mode,
                "reader_count": readers,
                "independent_invocation_count": len(matching),
                "statistical_unit": "one completed bounded microbenchmark invocation",
                "metrics": metrics,
            }
    return {
        "microbenchmark_schema_id": MICROBENCH_SCHEMA_ID,
        "comparison_design": COMPARISON_DESIGN,
        "claim_limitation": CLAIM_LIMITATION,
        "cohorts": cohorts,
    }


def capture_environment() -> JsonObject:
    """Collect non-secret host information needed to interpret a local run."""

    affinity: list[int] | None
    try:
        affinity = sorted(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        affinity = None
    load_average: list[float] | None
    try:
        load_average = list(os.getloadavg())
    except OSError:
        load_average = None
    return {
        "platform": platform.platform(),
        "python": sys.version,
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "available_processor_count": available_processor_count(),
        "cpu_affinity": affinity,
        "load_average": load_average,
        "pid": os.getpid(),
    }


def capture_background_state() -> JsonObject:
    """Capture bounded per-invocation background-load context."""

    load_average: list[float] | None
    try:
        load_average = list(os.getloadavg())
    except OSError:
        load_average = None
    return {"utc": utc_now(), "load_average": load_average}


def terminate_process_group(process: subprocess.Popen[bytes], grace_sec: int) -> int | None:
    """Stop a child process group with a bounded graceful interval."""

    try:
        os.killpg(process.pid, signal.SIGINT)
    except ProcessLookupError:
        return process.poll()
    try:
        return process.wait(timeout=grace_sec)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            return process.wait(timeout=grace_sec)
        except subprocess.TimeoutExpired:
            return process.poll()


def execute_invocation(
    command: list[str], stdout_path: Path, stderr_path: Path, timeout_sec: int, grace_sec: int
) -> ProcessResult:
    """Execute one invocation with a process-group deadline and preserved logs."""

    start_utc = utc_now()
    start_monotonic = time.monotonic()
    usage_before = resource.getrusage(resource.RUSAGE_CHILDREN)
    timed_out = False
    interrupted = False
    return_code: int | None = None
    with stdout_path.open("wb") as stdout_stream, stderr_path.open("wb") as stderr_stream:
        try:
            process = subprocess.Popen(
                command,
                stdout=stdout_stream,
                stderr=stderr_stream,
                start_new_session=True,
            )
        except OSError as exc:
            stderr_stream.write(f"runner could not start child: {exc}\n".encode("utf-8"))
        else:
            try:
                return_code = process.wait(timeout=timeout_sec)
            except subprocess.TimeoutExpired:
                timed_out = True
                return_code = terminate_process_group(process, grace_sec)
            except KeyboardInterrupt:
                interrupted = True
                return_code = terminate_process_group(process, grace_sec)
    usage_after = resource.getrusage(resource.RUSAGE_CHILDREN)
    return ProcessResult(
        return_code=return_code,
        timed_out=timed_out,
        interrupted=interrupted,
        utc_start=start_utc,
        utc_end=utc_now(),
        wall_duration_sec=time.monotonic() - start_monotonic,
        user_cpu_sec=max(0.0, usage_after.ru_utime - usage_before.ru_utime),
        system_cpu_sec=max(0.0, usage_after.ru_stime - usage_before.ru_stime),
    )


def compile_variant(
    compiler: str,
    source: Path,
    mode: str,
    binary: Path,
    log_path: Path,
    repository_root: Path,
) -> JsonObject:
    """Build one strict legacy/optimized binary while preserving compiler output."""

    command = [
        compiler,
        "-O2",
        "-std=c11",
        "-Wall",
        "-Wextra",
        "-Wpedantic",
        "-Wconversion",
        "-Wshadow",
        "-Wformat=2",
        "-Werror",
        "-pthread",
        f"-DORCHESTRA_SIGNAL_PUBLICATION_LEGACY={MODE_MACROS[mode]}",
        str(source),
        "-lm",
        "-o",
        str(binary),
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=repository_root,
            capture_output=True,
            text=True,
            timeout=60.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        log_path.write_text(str(exc) + "\n", encoding="utf-8")
        return {
            "mode": mode,
            "command_argv": command,
            "command_shell_escaped": shlex.join(command),
            "return_code": None,
            "timed_out_or_execution_failed": True,
            "stdout": "",
            "stderr": str(exc),
            "binary_created": False,
        }
    combined = completed.stdout + completed.stderr
    log_path.write_text(combined, encoding="utf-8")
    return {
        "mode": mode,
        "command_argv": command,
        "command_shell_escaped": shlex.join(command),
        "return_code": completed.returncode,
        "timed_out_or_execution_failed": False,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "binary_created": binary.is_file(),
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse bounded microbenchmark controls."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("tools/benchmark/signal_publication_microbenchmark.c"),
    )
    parser.add_argument(
        "--canonical-source",
        type=Path,
        default=Path("orchestra_paper_cpu_demo/orchestra_paper_cpu.c"),
    )
    parser.add_argument("--cc", default=os.environ.get("CC", "cc"))
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--iterations", type=int, default=5_000)
    parser.add_argument("--warmup", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20_260_804)
    parser.add_argument("--max-readers", type=int, default=8)
    parser.add_argument("--startup-timeout-ms", type=int, default=1_000)
    parser.add_argument("--max-runtime-ms", type=int, default=3_000)
    parser.add_argument("--drain-reads", type=int, default=4)
    parser.add_argument("--timeout-sec", type=int, default=10)
    parser.add_argument("--timeout-grace-sec", type=int, default=2)
    return parser.parse_args(argv)


def require_range(name: str, value: int, minimum: int, maximum: int) -> None:
    """Validate a bounded integer command-line setting."""

    if value < minimum or value > maximum:
        raise MicrobenchmarkError(f"{name}={value} is outside {minimum}..{maximum}")


def validate_args(args: argparse.Namespace) -> None:
    """Validate every user-facing bound before creating execution state."""

    require_range("repetitions", args.repetitions, 2, 10)
    require_range("iterations", args.iterations, 100, 200_000)
    require_range("warmup", args.warmup, 0, 10_000)
    require_range("seed", args.seed, 1, 9_223_372_036_854_775_807)
    require_range("max_readers", args.max_readers, 1, MAX_RUNNER_READERS)
    require_range("startup_timeout_ms", args.startup_timeout_ms, 10, 5_000)
    require_range("max_runtime_ms", args.max_runtime_ms, 100, 10_000)
    require_range("drain_reads", args.drain_reads, 0, 128)
    require_range("timeout_grace_sec", args.timeout_grace_sec, 1, 10)
    require_range("timeout_sec", args.timeout_sec, 2, 30)
    required_timeout_ms = (
        args.max_runtime_ms + args.startup_timeout_ms + INTERNAL_JOIN_BUDGET_MS
    )
    if args.timeout_sec * 1_000 < required_timeout_ms:
        raise MicrobenchmarkError(
            "timeout_sec must cover startup, internal runtime, and bounded join cleanup"
        )


def write_invocation_csv(path: Path, summaries: list[JsonObject]) -> None:
    """Write one independent-invocation row without conflating runs and samples."""

    fieldnames = (
        "run_id",
        "publication_mode",
        "readers",
        "repetition",
        "seed",
        *INVOCATION_DERIVED_METRIC_NAMES,
    )
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for summary in summaries:
            row = {
                "run_id": summary["run_id"],
                "publication_mode": summary["publication_mode"],
                "readers": summary["readers"],
                "repetition": summary["repetition"],
                "seed": summary["seed"],
                **summary["derived_metrics"],
            }
            writer.writerow(row)


def run_microbenchmark(args: argparse.Namespace) -> int:
    """Build both variants, execute bounded invocations, and write provenance."""

    if not sys.platform.startswith("linux"):
        raise MicrobenchmarkError("the signal-publication microbenchmark requires Linux")
    validate_args(args)
    repository_root = args.repository_root.expanduser().resolve()
    if not repository_root.is_dir():
        raise MicrobenchmarkError(f"repository root is not a directory: {repository_root}")
    source = resolve_regular_file(repository_root / args.source, "microbenchmark source")
    canonical_source = resolve_regular_file(
        repository_root / args.canonical_source, "canonical signal source"
    )
    compiler = shutil.which(args.cc)
    if compiler is None:
        raise MicrobenchmarkError(f"C compiler is unavailable: {args.cc}")
    output_dir = args.output_dir.expanduser().resolve()
    if output_dir.exists():
        raise MicrobenchmarkError(f"output directory already exists: {output_dir}")

    host_processors = available_processor_count()
    reader_counts = bounded_reader_counts(host_processors, args.max_readers)
    output_dir.mkdir(parents=True, exist_ok=False)
    build_dir = output_dir / "build"
    runs_dir = output_dir / "runs"
    processed_dir = output_dir / "processed"
    build_dir.mkdir()
    runs_dir.mkdir()
    processed_dir.mkdir()

    source_hash_start = sha256_file(source)
    canonical_hash_start = sha256_file(canonical_source)
    benchmark_start = utc_now()
    provenance: JsonObject = {
        "microbenchmark_schema_id": MICROBENCH_SCHEMA_ID,
        "comparison_design": COMPARISON_DESIGN,
        "claim_limitation": CLAIM_LIMITATION,
        "benchmark_start_utc": benchmark_start,
        "repository_root": str(repository_root),
        "output_directory": str(output_dir),
        "host_processor_count": host_processors,
        "configured_max_readers": args.max_readers,
        "reader_counts": list(reader_counts),
        "inputs": {
            "microbenchmark_source": {"path": str(source), "sha256": source_hash_start},
            "canonical_source": {"path": str(canonical_source), "sha256": canonical_hash_start},
        },
        "controls": {
            "repetitions": args.repetitions,
            "iterations": args.iterations,
            "warmup": args.warmup,
            "base_seed": args.seed,
            "startup_timeout_ms": args.startup_timeout_ms,
            "max_runtime_ms": args.max_runtime_ms,
            "drain_reads": args.drain_reads,
            "internal_join_budget_ms": INTERNAL_JOIN_BUDGET_MS,
            "external_timeout_sec": args.timeout_sec,
            "external_timeout_grace_sec": args.timeout_grace_sec,
        },
        "environment": capture_environment(),
    }
    write_json(output_dir / "provenance.json", provenance)

    build_records: list[JsonObject] = []
    binaries: dict[str, Path] = {}
    for mode in PUBLICATION_MODES:
        binary = build_dir / f"signal_publication_microbenchmark_{mode}"
        build_record = compile_variant(
            compiler,
            source,
            mode,
            binary,
            build_dir / f"compile_{mode}.log",
            repository_root,
        )
        if build_record["return_code"] == 0 and build_record["binary_created"] is True:
            build_record["binary_sha256"] = sha256_file(binary)
            binaries[mode] = binary
        else:
            build_record["binary_sha256"] = None
        build_records.append(build_record)
    write_json(build_dir / "build_records.json", build_records)
    if len(binaries) != len(PUBLICATION_MODES):
        result = {
            "status": "build_failed",
            "benchmark_start_utc": benchmark_start,
            "benchmark_end_utc": utc_now(),
            "build_records": build_records,
            "claim_limitation": CLAIM_LIMITATION,
        }
        write_json(output_dir / "benchmark_result.json", result)
        return 1

    run_records: list[JsonObject] = []
    summaries: list[JsonObject] = []
    interrupted = False
    execution_index = 0
    for repetition in range(1, args.repetitions + 1):
        for readers in reader_counts:
            seed = args.seed + repetition * 1_000 + readers
            for mode in PUBLICATION_MODES:
                execution_index += 1
                run_id = f"rep_{repetition:02d}_readers_{readers}_{mode}"
                stdout_path = runs_dir / f"{run_id}.stdout.json"
                stderr_path = runs_dir / f"{run_id}.stderr.log"
                command = [
                    str(binaries[mode]),
                    "--readers",
                    str(readers),
                    "--iterations",
                    str(args.iterations),
                    "--warmup",
                    str(args.warmup),
                    "--seed",
                    str(seed),
                    "--startup-timeout-ms",
                    str(args.startup_timeout_ms),
                    "--max-runtime-ms",
                    str(args.max_runtime_ms),
                    "--drain-reads",
                    str(args.drain_reads),
                ]
                background_before = capture_background_state()
                process = execute_invocation(
                    command,
                    stdout_path,
                    stderr_path,
                    args.timeout_sec,
                    args.timeout_grace_sec,
                )
                background_after = capture_background_state()
                measurement: JsonObject | None = None
                validation_issues: list[str] = []
                if stdout_path.is_file():
                    try:
                        measurement = read_json_measurement(stdout_path)
                        validation_issues = validate_measurement(
                            measurement, mode, readers, args.iterations, seed
                        )
                    except MicrobenchmarkError as exc:
                        validation_issues.append(str(exc))
                else:
                    validation_issues.append("runner did not preserve stdout")
                source_hash_after = sha256_file(source)
                canonical_hash_after = sha256_file(canonical_source)
                binary_hash_after = sha256_file(binaries[mode])
                expected_binary_hash = str(
                    next(
                        record["binary_sha256"]
                        for record in build_records
                        if record["mode"] == mode
                    )
                )
                hash_stable = (
                    source_hash_after == source_hash_start
                    and canonical_hash_after == canonical_hash_start
                    and binary_hash_after == expected_binary_hash
                )
                included = (
                    process.return_code == 0
                    and not process.timed_out
                    and not process.interrupted
                    and not validation_issues
                    and hash_stable
                    and measurement is not None
                )
                exclusion_reasons: list[str] = []
                if process.return_code != 0:
                    exclusion_reasons.append(f"return_code={process.return_code}")
                if process.timed_out:
                    exclusion_reasons.append("external_timeout")
                if process.interrupted:
                    exclusion_reasons.append("operator_interrupt")
                if validation_issues:
                    exclusion_reasons.append("measurement_validation_failed")
                if not hash_stable:
                    exclusion_reasons.append("input_or_binary_changed_during_run")
                record: JsonObject = {
                    "run_id": run_id,
                    "execution_index": execution_index,
                    "publication_mode": mode,
                    "readers": readers,
                    "repetition": repetition,
                    "seed": seed,
                    "command_argv": command,
                    "command_shell_escaped": shlex.join(command),
                    "process": asdict(process),
                    "background_before": background_before,
                    "background_after": background_after,
                    "raw_stdout": {
                        "path": str(stdout_path.relative_to(output_dir)),
                        "sha256": sha256_file(stdout_path),
                    },
                    "raw_stderr": {
                        "path": str(stderr_path.relative_to(output_dir)),
                        "sha256": sha256_file(stderr_path),
                    },
                    "measurement": measurement,
                    "measurement_validation_issues": validation_issues,
                    "source_sha256_after": source_hash_after,
                    "canonical_source_sha256_after": canonical_hash_after,
                    "binary_sha256_after": binary_hash_after,
                    "inputs_stable": hash_stable,
                    "included_in_summary": included,
                    "exclusion_reasons": exclusion_reasons,
                }
                write_json(runs_dir / f"{run_id}.json", record)
                run_records.append(record)
                if included and measurement is not None:
                    summaries.append(
                        {
                            "run_id": run_id,
                            "publication_mode": mode,
                            "readers": readers,
                            "repetition": repetition,
                            "seed": seed,
                            "derived_metrics": make_invocation_summary(measurement),
                        }
                    )
                if process.interrupted:
                    interrupted = True
                    break
            if interrupted:
                break
        if interrupted:
            break

    aggregate = aggregate_summaries(summaries)
    write_json(processed_dir / "invocation_summaries.json", summaries)
    write_invocation_csv(processed_dir / "invocation_summaries.csv", summaries)
    write_json(processed_dir / "summary.json", aggregate)
    expected_run_count = args.repetitions * len(reader_counts) * len(PUBLICATION_MODES)
    failures = sum(1 for record in run_records if record["included_in_summary"] is not True)
    result: JsonObject = {
        "status": (
            "complete"
            if not interrupted and failures == 0 and len(run_records) == expected_run_count
            else "complete_with_failures"
        ),
        "microbenchmark_schema_id": MICROBENCH_SCHEMA_ID,
        "comparison_design": COMPARISON_DESIGN,
        "claim_limitation": CLAIM_LIMITATION,
        "benchmark_start_utc": benchmark_start,
        "benchmark_end_utc": utc_now(),
        "expected_run_count": expected_run_count,
        "attempted_run_count": len(run_records),
        "validated_run_count": len(summaries),
        "failed_or_excluded_run_count": failures,
        "operator_interrupted": interrupted,
        "source_sha256_start": source_hash_start,
        "source_sha256_end": sha256_file(source),
        "canonical_source_sha256_start": canonical_hash_start,
        "canonical_source_sha256_end": sha256_file(canonical_source),
        "binary_hashes": {
            mode: sha256_file(binary) for mode, binary in binaries.items()
        },
        "processed_outputs": {
            "invocation_summaries_json": "processed/invocation_summaries.json",
            "invocation_summaries_csv": "processed/invocation_summaries.csv",
            "summary_json": "processed/summary.json",
        },
    }
    write_json(output_dir / "benchmark_result.json", result)
    return 0 if result["status"] == "complete" else 1


def main(argv: list[str] | None = None) -> int:
    """CLI entry point with configuration errors distinct from failed runs."""

    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        return run_microbenchmark(args)
    except MicrobenchmarkError as exc:
        print(f"microbenchmark configuration error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
