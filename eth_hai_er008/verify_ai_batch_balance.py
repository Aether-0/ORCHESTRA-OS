#!/usr/bin/env python3
"""Verify ER-008 from the pinned task/advice source and released task orders.

This emits task-order aggregates only. It does not read participant-level data.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

PINNED_COMMIT = "008f9833ab8c4c23ed94908e0108053a2240a100"
EXPECTED_PER_BATCH = 4


def load_util(repo: Path):
    path = repo / "data_analysis" / "util.py"
    spec = importlib.util.spec_from_file_location("eth_hai_er008_util", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.dont_write_bytecode = True
    spec.loader.exec_module(module)
    module.data_folder = str(repo / "anonymous_data")
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    repo = args.repo.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    util = load_util(repo)
    answers = util.load_answers()

    rows: List[Dict[str, Any]] = []
    failures: List[str] = []
    all_substantive = set()

    for order_id in sorted(util.question_order_dict):
        sequence = [int(x) for x in util.question_order_dict[order_id]]
        if len(sequence) != 16 or len(set(sequence)) != 16:
            failures.append(f"order {order_id}: expected 16 unique substantive tasks")
        if any(x in {6, 11, 18} for x in sequence):
            failures.append(f"order {order_id}: attention task present after removal")
        all_substantive.update(sequence)

        first = sequence[:6]
        middle = sequence[6:-6]
        second = sequence[-6:]

        def correct_count(task_ids: List[int]) -> int:
            return sum(1 for task_id in task_ids if answers[task_id][0] == answers[task_id][1])

        first_correct = correct_count(first)
        middle_correct = correct_count(middle)
        second_correct = correct_count(second)
        passed = first_correct == EXPECTED_PER_BATCH and second_correct == EXPECTED_PER_BATCH
        if not passed:
            failures.append(
                f"order {order_id}: first={first_correct}, second={second_correct}, expected 4 each"
            )

        rows.append({
            "order_id": order_id,
            "first_batch_task_ids": ",".join(map(str, first)),
            "first_batch_ai_correct": first_correct,
            "middle_task_ids": ",".join(map(str, middle)),
            "middle_ai_correct": middle_correct,
            "second_batch_task_ids": ",".join(map(str, second)),
            "second_batch_ai_correct": second_correct,
            "passes_er008": passed,
        })

    if all_substantive != set(answers) - {6, 11, 18}:
        failures.append("released task orders do not span the full substantive task set")

    report = {
        "schema_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "repository": "RichardHGL/CHI2023_DKE",
        "pinned_commit": PINNED_COMMIT,
        "expected_ai_correct_per_experimental_batch": EXPECTED_PER_BATCH,
        "task_order_count": len(rows),
        "substantive_task_count": len(all_substantive),
        "all_orders_pass": not failures,
        "failures": failures,
        "participant_level_data_read": False,
        "participant_level_data_emitted": False,
        "rows": rows,
    }
    (out / "er008_verification.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    header = [
        "order_id", "first_batch_task_ids", "first_batch_ai_correct",
        "middle_task_ids", "middle_ai_correct", "second_batch_task_ids",
        "second_batch_ai_correct", "passes_er008",
    ]
    with (out / "er008_task_order_crosswalk.tsv").open("w", encoding="utf-8", newline="\n") as fh:
        fh.write("\t".join(header) + "\n")
        for row in rows:
            fh.write("\t".join(str(row[h]) for h in header) + "\n")

    status = [
        "# ER-008 Task-Balance Verification",
        "",
        f"- Result: **{'PASS' if not failures else 'FAIL'}**",
        f"- Released task orders checked: **{len(rows)}**",
        f"- Expected AI-correct tasks per first/second batch: **{EXPECTED_PER_BATCH}**",
        "- Participant-level data read: **No**",
        "- Participant-level data emitted: **No**",
    ]
    (out / "GATE_STATUS.md").write_text("\n".join(status) + "\n", encoding="utf-8")

    print(json.dumps({
        "passed": not failures,
        "task_orders_checked": len(rows),
        "expected_per_batch": EXPECTED_PER_BATCH,
        "failures": failures,
    }, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
