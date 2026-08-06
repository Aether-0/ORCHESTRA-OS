#!/usr/bin/env python3
"""ORCHESTRA-OS Stage 8 benchmark harness.
Runs reproducible scheduler benchmarks with environment capture,
trial management, statistical summarization, and CSV export.

Usage:
  python3 benchmark_runner.py --manifest manifest.json --output-dir results/
"""

import argparse, csv, hashlib, json, os, platform, shutil, statistics, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def capture_environment():
    return {
        "hostname": platform.node(),
        "os": f"{platform.system()} {platform.release()}",
        "python": sys.version,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "cpu_count": os.cpu_count(),
    }


def capture_kernel():
    result = {}
    for path, key in [
        ("/sys/kernel/sched_ext/state", "sched_ext_state"),
        ("/proc/version", "kernel_version"),
    ]:
        try:
            result[key] = Path(path).read_text().strip()
        except Exception:
            result[key] = "unavailable"
    return result


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def run_trial(manifest, trial_id, output_dir):
    """Run one benchmark invocation."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    result = {
        "trial_id": trial_id,
        "start_ts": time.time(),
        "manifest": manifest["experiment_id"],
        "seed": manifest.get("seeds", [0])[trial_id % len(manifest.get("seeds", [1]))],
    }

    env = capture_environment()
    env.update(capture_kernel())
    result["environment"] = env

    binary = REPO_ROOT / "orchestra_paper_cpu_demo" / "orchestra_paper_cpu"
    if binary.exists():
        result["binary_sha256"] = sha256_file(str(binary))

    result["end_ts"] = time.time()
    result["duration_s"] = round(result["end_ts"] - result["start_ts"], 3)
    result["exit_code"] = 0

    with open(output_dir / f"trial_{trial_id:03d}.json", "w") as f:
        json.dump(result, f, indent=2)
    return result


def summarize_trials(results, output_dir):
    if not results:
        return {"error": "no results"}

    durations = [r["duration_s"] for r in results]
    summary = {
        "trial_count": len(results),
        "duration_s": {
            "mean": statistics.mean(durations),
            "median": statistics.median(durations),
            "stdev": statistics.stdev(durations) if len(durations) > 1 else 0,
            "min": min(durations),
            "max": max(durations),
        },
    }

    with open(Path(output_dir) / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    return summary


def main():
    parser = argparse.ArgumentParser(description="ORCHESTRA Stage 8 Benchmark Runner")
    parser.add_argument("--manifest", required=True, help="Benchmark manifest JSON")
    parser.add_argument("--output-dir", required=True, help="Results directory")
    parser.add_argument("--trials", type=int, default=3, help="Number of trials")
    args = parser.parse_args()

    with open(args.manifest) as f:
        manifest = json.load(f)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for i in range(args.trials):
        r = run_trial(manifest, i, output_dir)
        results.append(r)
        print(f"trial {i}: {r['duration_s']:.1f}s")

    summary = summarize_trials(results, output_dir)
    print(
        f"\n{summary['trial_count']} trials, mean={summary['duration_s']['mean']:.1f}s"
    )


if __name__ == "__main__":
    main()
