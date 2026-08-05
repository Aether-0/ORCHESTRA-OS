#!/usr/bin/env python3
"""Run the repository regression suite and preserve a bounded evidence record."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Final


RESULT_SCHEMA: Final = "orchestra.test_run/v1"
INPUT_PATHS: Final = (
    "Makefile",
    "orchestra_paper_cpu_demo/Makefile",
    "orchestra_paper_cpu_demo/orchestra_paper_cpu.c",
    "orchestra_paper_cpu_demo/README.md",
    "tests/unit/run.sh",
    "tests/unit/test_orchestra_paper_cpu.c",
    "tests/unit/test_signal_publication_stress.c",
    "tests/unit/test_benchmark_validator.py",
    "tests/unit/test_signal_publication_microbenchmark_runner.py",
    "tests/integration/run.sh",
    "tests/integration/test_signal_publication_integration.c",
    "tests/integration/validate_paper_cpu_csv.py",
    "tools/benchmark/run_paper_cpu_benchmark.py",
    "tools/benchmark/signal_publication_microbenchmark.c",
    "tools/benchmark/run_signal_publication_microbenchmark.py",
    "docs/adr/0002-userspace-signal-frame-contract.md",
    "docs/adr/0006-generation-stamped-signal-publication.md",
    "tools/plotting/plot_paper_cpu_smoke.py",
    "tools/plotting/plot_release_readiness.py",
    "tools/reporting/build_release_readiness_docx.py",
    "tools/testing/capture_test_run.py",
    "tools/testing/index_test_artifacts.py",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root containing the top-level Makefile.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="New directory for make-test.log and test-result.json.",
    )
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def command_version(executable: str, *arguments: str) -> dict[str, object]:
    path = shutil.which(executable)
    if path is None:
        return {"available": False, "path": None, "version": None}
    completed = subprocess.run(
        [path, *arguments],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=10,
    )
    first_line = completed.stdout.splitlines()[0] if completed.stdout else ""
    return {
        "available": True,
        "path": path,
        "return_code": completed.returncode,
        "version": first_line,
    }


def git_identity(repository_root: Path) -> dict[str, object]:
    git = shutil.which("git")
    if git is None:
        return {"available": False, "status": "git-not-installed"}
    top = subprocess.run(
        [git, "-C", str(repository_root), "rev-parse", "--show-toplevel"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=10,
    )
    if top.returncode != 0:
        return {"available": False, "status": "not-a-git-worktree"}
    commit = subprocess.run(
        [git, "-C", str(repository_root), "rev-parse", "HEAD"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=10,
    )
    status = subprocess.run(
        [git, "-C", str(repository_root), "status", "--porcelain=v1"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=10,
    )
    return {
        "available": True,
        "status": "worktree",
        "commit": commit.stdout.strip() if commit.returncode == 0 else None,
        "dirty": bool(status.stdout.strip()) if status.returncode == 0 else None,
    }


def input_hashes(repository_root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative in INPUT_PATHS:
        path = repository_root / relative
        if not path.is_file():
            raise FileNotFoundError(f"test input is missing: {path}")
        hashes[relative] = sha256_file(path)
    return hashes


def run_tests(
    repository_root: Path, log_path: Path, integration_artifact_dir: Path
) -> tuple[int, float]:
    start = time.monotonic()
    environment = os.environ.copy()
    environment["ORCHESTRA_INTEGRATION_ARTIFACT_DIR"] = str(
        integration_artifact_dir
    )
    process = subprocess.Popen(
        ["make", "test"],
        cwd=repository_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=environment,
    )
    if process.stdout is None:
        raise RuntimeError("failed to capture make test output")
    with log_path.open("wb") as log:
        while True:
            chunk = process.stdout.read(64 * 1024)
            if not chunk:
                break
            log.write(chunk)
            sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()
    return_code = process.wait()
    return return_code, time.monotonic() - start


def main() -> int:
    args = parse_args()
    repository_root = args.repository_root.resolve()
    output_dir = args.output_dir
    if not output_dir.is_absolute():
        output_dir = repository_root / output_dir
    if output_dir.exists():
        raise FileExistsError(f"output directory already exists: {output_dir}")
    if not (repository_root / "Makefile").is_file():
        raise FileNotFoundError(f"top-level Makefile not found under {repository_root}")

    hashes_before = input_hashes(repository_root)
    output_dir.mkdir(parents=True)
    log_path = output_dir / "make-test.log"
    integration_artifact_dir = output_dir / "integration"
    start_utc = utc_now()
    return_code, duration_seconds = run_tests(
        repository_root, log_path, integration_artifact_dir
    )
    end_utc = utc_now()
    hashes_after = input_hashes(repository_root)

    result = {
        "schema": RESULT_SCHEMA,
        "status": "passed" if return_code == 0 else "failed",
        "claim_boundary": (
            "Regression evidence for the named repository tests only; this does not "
            "upgrade the userspace-validated maturity class."
        ),
        "command": ["make", "test"],
        "return_code": return_code,
        "start_utc": start_utc,
        "end_utc": end_utc,
        "duration_seconds": duration_seconds,
        "repository_root": str(repository_root),
        "repository_identity": git_identity(repository_root),
        "environment": {
            "hostname": platform.node(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": sys.version.splitlines()[0],
            "effective_uid": os.geteuid(),
            "gcc": command_version("gcc", "--version"),
            "clang": command_version("clang", "--version"),
            "make": command_version("make", "--version"),
        },
        "input_sha256_before": hashes_before,
        "input_sha256_after": hashes_after,
        "inputs_unchanged": hashes_before == hashes_after,
        "log": {
            "path": log_path.name,
            "bytes": log_path.stat().st_size,
            "sha256": sha256_file(log_path),
            "stderr_merged": True,
        },
        "integration_artifacts": {
            "path": integration_artifact_dir.name,
            "preserved": integration_artifact_dir.is_dir(),
            "files": sorted(
                path.name for path in integration_artifact_dir.glob("*") if path.is_file()
            ),
        },
    }
    result_path = output_dir / "test-result.json"
    result_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"captured {result_path}")
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
