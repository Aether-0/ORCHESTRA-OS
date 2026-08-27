#!/usr/bin/env python3
"""Execute the first independent clean-reimplementation gate.

The output is aggregate only. Participant-level rows and identifiers never leave the
private runner workspace.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, List, Tuple

from eth_hai_clean.core import (
    TASK_ORDERS,
    build_clean_metric_frame,
    load_task_answers,
    summarize_clean_frame,
)

GOLDEN_CONDITIONS = {
    "no tutorial, no xai": 63,
    "with tutorial, no xai": 62,
    "no tutorial, with xai": 62,
    "with tutorial, with xai": 62,
}
GOLDEN_FIRST = {
    "no tutorial, no xai": {"Under": 16, "Accurate": 24, "Over": 23},
    "with tutorial, no xai": {"Under": 19, "Accurate": 19, "Over": 24},
    "no tutorial, with xai": {"Under": 19, "Accurate": 15, "Over": 28},
    "with tutorial, with xai": {"Under": 18, "Accurate": 18, "Over": 26},
}
GOLDEN_SECOND = {
    "no tutorial, no xai": {"Under": 27, "Accurate": 12, "Over": 24},
    "with tutorial, no xai": {"Under": 24, "Accurate": 16, "Over": 22},
    "no tutorial, with xai": {"Under": 24, "Accurate": 16, "Over": 22},
    "with tutorial, with xai": {"Under": 20, "Accurate": 15, "Over": 27},
}
GOLDEN_OVERALL_GROUPS = {"Under": 72, "Accurate": 76, "Over": 101}
GOLDEN_DESCRIPTIVES = {
    "ATI": (3.726, 3, 0.99, 2),
    "TiA-Propensity": (2.953, 3, 0.60, 2),
    "Accuracy": (0.569, 3, 0.16, 2),
    "Agreement_fraction": (0.665, 3, 0.17, 2),
    "switching_fraction": (0.453, 3, 0.27, 2),
    "RAIR": (0.514, 3, 0.31, 2),
    "RSR": (0.565, 3, 0.43, 2),
    "TiA-Trust-first": (3.112, 3, 0.85, 2),
    "TiA-Trust-second": (3.171, 3, 0.82, 2),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    frame = build_clean_metric_frame(repo, undefined_ratio="zero")
    summary = summarize_clean_frame(frame)

    checks: List[Dict[str, object]] = []

    def check(name: str, observed, expected, passed: bool, note: str = "") -> None:
        checks.append({
            "check": name,
            "observed": observed,
            "expected": expected,
            "passed": bool(passed),
            "note": note,
        })

    check("sample_n", summary["sample_n"], 249, summary["sample_n"] == 249)
    check(
        "condition_counts", summary["condition_counts"], GOLDEN_CONDITIONS,
        summary["condition_counts"] == GOLDEN_CONDITIONS,
    )
    check(
        "first_batch_calibration_by_condition",
        summary["first_batch_calibration_by_condition"], GOLDEN_FIRST,
        summary["first_batch_calibration_by_condition"] == GOLDEN_FIRST,
    )
    check(
        "second_batch_calibration_by_condition",
        summary["second_batch_calibration_by_condition"], GOLDEN_SECOND,
        summary["second_batch_calibration_by_condition"] == GOLDEN_SECOND,
    )
    check(
        "first_batch_calibration_overall",
        summary["first_batch_calibration_overall"], GOLDEN_OVERALL_GROUPS,
        summary["first_batch_calibration_overall"] == GOLDEN_OVERALL_GROUPS,
    )

    descriptive_rows: List[Dict[str, object]] = []
    for label, (expected_mean, mean_digits, expected_sd, sd_digits) in GOLDEN_DESCRIPTIVES.items():
        observed = summary["descriptives"][label]
        mean_match = round(observed["mean"], mean_digits) == round(expected_mean, mean_digits)
        sd_match = round(observed["sd_sample"], sd_digits) == round(expected_sd, sd_digits)
        check(
            "descriptive.%s" % label,
            {"mean": observed["mean"], "sd_sample": observed["sd_sample"]},
            {"mean": expected_mean, "sd_sample": expected_sd},
            mean_match and sd_match,
            "Compared at the direct-reproduction display precision.",
        )
        descriptive_rows.append({
            "metric": label,
            "observed_mean": observed["mean"],
            "expected_mean": expected_mean,
            "mean_digits": mean_digits,
            "observed_sd": observed["sd_sample"],
            "expected_sd": expected_sd,
            "sd_digits": sd_digits,
            "status": "Exact" if mean_match and sd_match else "Mismatch",
        })

    task_answers = load_task_answers(repo)
    er008_rows: List[Dict[str, object]] = []
    for order_id, sequence in sorted(TASK_ORDERS.items()):
        first = sequence[:6]
        middle = sequence[6:-6]
        second = sequence[-6:]
        count = lambda ids: sum(1 for task_id in ids if task_answers[task_id][0] == task_answers[task_id][1])
        first_count, middle_count, second_count = count(first), count(middle), count(second)
        er008_rows.append({
            "order_id": order_id,
            "first_ai_correct": first_count,
            "middle_ai_correct": middle_count,
            "second_ai_correct": second_count,
            "passes_er008": first_count == 4 and second_count == 4,
        })
    check(
        "er008_all_task_orders",
        er008_rows,
        "first=4 and second=4 for all 10 orders",
        all(row["passes_er008"] for row in er008_rows),
    )

    all_pass = all(bool(item["passed"]) for item in checks)
    output = {
        "schema_version": "0.1",
        "stage": "independent clean core equivalence gate",
        "passed": all_pass,
        "checks_passed": sum(bool(item["passed"]) for item in checks),
        "checks_total": len(checks),
        "summary": summary,
        "er008": er008_rows,
        "checks": checks,
        "upstream_util_imported": False,
        "participant_level_data_emitted": False,
    }
    (out / "clean_core_summary.json").write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    with (out / "clean_core_equivalence.tsv").open("w", encoding="utf-8", newline="\n") as fh:
        writer = csv.DictWriter(fh, fieldnames=[
            "metric", "observed_mean", "expected_mean", "mean_digits",
            "observed_sd", "expected_sd", "sd_digits", "status",
        ], delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(descriptive_rows)

    with (out / "er008_clean_crosscheck.tsv").open("w", encoding="utf-8", newline="\n") as fh:
        writer = csv.DictWriter(fh, fieldnames=[
            "order_id", "first_ai_correct", "middle_ai_correct",
            "second_ai_correct", "passes_er008",
        ], delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(er008_rows)

    with (out / "zero_denominator_counts.tsv").open("w", encoding="utf-8", newline="\n") as fh:
        fh.write("metric\tcount\n")
        for metric, count_value in summary["zero_denominator_counts"].items():
            fh.write("%s\t%s\n" % (metric, count_value))

    (out / "GATE_STATUS.md").write_text(
        "# Independent Clean Core Gate\n\n"
        "- Result: **%s**\n" % ("PASS" if all_pass else "FAIL")
        + "- Golden aggregate checks: **%d/%d passed**\n" % (
            sum(bool(item["passed"]) for item in checks), len(checks)
        )
        + "- Upstream `util.py` imported: **No**\n"
        + "- Participant-level data emitted: **No**\n"
        + "- Robustness modifications applied: **No — equivalence mode only**\n",
        encoding="utf-8",
    )

    print(json.dumps({
        "passed": all_pass,
        "checks_passed": output["checks_passed"],
        "checks_total": output["checks_total"],
        "sample_n": summary["sample_n"],
    }, indent=2, sort_keys=True))
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
