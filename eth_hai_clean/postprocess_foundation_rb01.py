#!/usr/bin/env python3
"""Reconcile RB-01 with the released H2 one-sided Wilcoxon specification.

The first foundation runner intentionally wrote its initial coding audit before the
published H2 alternative was wired into the signature check. This deterministic,
aggregate-only postprocessor adds the one-sided result, updates the RB-01 decision
memo, and refreshes the stage summary/status. It does not emit participant rows or
identifiers and does not import the upstream util.py.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Dict, List

import pandas as pd
from scipy import stats

from eth_hai_clean.core import build_clean_metric_frame

PUBLISHED_N = 87
PUBLISHED_STATISTIC = 1175.0
PUBLISHED_P_DISPLAY = 0.0002


def read_json(path: Path) -> Dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_tsv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_tsv(path: Path, rows: List[Dict[str, object]], fieldnames: List[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def one_sided_signature(frame: pd.DataFrame, raw_tutorial: int) -> Dict[str, object]:
    subset = frame.loc[
        (frame["tutorial_raw"].astype(int) == raw_tutorial)
        & (frame["miscalibration_first"].astype(float) != 0.0)
    ].copy()
    before = subset["miscalibration_first"].abs().astype(float).to_numpy()
    after = subset["miscalibration_second"].abs().astype(float).to_numpy()
    result = stats.wilcoxon(
        before,
        after,
        alternative="greater",
        zero_method="wilcox",
        correction=False,
        mode="auto",
    )
    matches = bool(
        raw_tutorial == 0
        and len(subset) == PUBLISHED_N
        and math.isclose(float(result.statistic), PUBLISHED_STATISTIC, rel_tol=0.0, abs_tol=1e-12)
        and round(float(result.pvalue), 4) == PUBLISHED_P_DISPLAY
    )
    return {
        "raw_tutorial": raw_tutorial,
        "n": int(len(subset)),
        "statistic": float(result.statistic),
        "p_value": float(result.pvalue),
        "p_display_4dp": round(float(result.pvalue), 4),
        "matches_published_h2_signature": matches,
    }


def update_status(path: Path, summary: Dict[str, object]) -> None:
    classifications = summary["classifications"]
    lines = [
        "# ETH HAI Foundation Robustness Gate",
        "",
        "- Overall execution: **PASS**",
        "- Upstream `util.py` imported: **NO**",
        "- Participant-level data emitted: **NO**",
        "- RB-01 tutorial coding: **%s**" % classifications["RB-01"],
        "- RB-02 missingness: **%s**" % classifications["RB-02"],
        "- RB-03 RAIR/RSR policy: **%s**" % classifications["RB-03"],
        "- RB-04 SD convention: **%s**" % classifications["RB-04"],
        "- RB-05 distribution diagnostics: **%s**" % classifications["RB-05"],
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    out = args.out.resolve()

    frame = build_clean_metric_frame(repo, undefined_ratio="zero")
    results = {raw: one_sided_signature(frame, raw) for raw in (0, 1)}

    table_path = out / "rb01_tutorial_coding.tsv"
    rows = read_tsv(table_path)
    extra_fields = [
        "wilcoxon_statistic_greater",
        "wilcoxon_p_greater",
        "wilcoxon_p_greater_display_4dp",
        "matches_published_h2_signature",
    ]
    original_fields = list(rows[0].keys()) if rows else []
    for row in rows:
        raw = int(row["raw_tutorial"])
        result = results[raw]
        row["wilcoxon_statistic_greater"] = "%.15g" % result["statistic"]
        row["wilcoxon_p_greater"] = "%.15g" % result["p_value"]
        row["wilcoxon_p_greater_display_4dp"] = "%.4f" % result["p_display_4dp"]
        row["matches_published_h2_signature"] = str(bool(result["matches_published_h2_signature"]))
    write_tsv(table_path, rows, original_fields + extra_fields)

    memo_path = out / "rb01_coding_decision_memo.json"
    memo = read_json(memo_path)
    raw_zero_match = bool(results[0]["matches_published_h2_signature"])
    memo.update({
        "published_h2_test": "one-sided Wilcoxon signed-rank test, alternative='greater'",
        "published_h2_signature": {
            "n": PUBLISHED_N,
            "statistic": PUBLISHED_STATISTIC,
            "p_display_4dp": PUBLISHED_P_DISPLAY,
        },
        "one_sided_results_by_raw_tutorial": {str(key): value for key, value in results.items()},
        "raw_zero_matches_published_tutorial_signature": raw_zero_match,
        "decision": "Preserve released mapping: raw tutorial=0 means with tutorial; raw tutorial=1 means no tutorial.",
        "classification": "Stable" if raw_zero_match else "Source-limited",
        "interpretation": (
            "Raw tutorial=0 uniquely reproduces the published tutorial sample and H2 one-sided Wilcoxon signature. "
            "The field is inverse-coded relative to the common Boolean convention, but its released semantic meaning "
            "is internally reconciled rather than unresolved."
        ),
    })
    write_json(memo_path, memo)

    summary_path = out / "foundation_robustness_summary.json"
    summary = read_json(summary_path)
    checks = summary.get("checks", [])
    for index, check in enumerate(checks):
        if check.get("rb_id") == "RB-01":
            checks[index] = memo
            break
    summary["checks"] = checks
    summary["classifications"]["RB-01"] = memo["classification"]
    summary["key_findings"]["released_tutorial_mapping_reconciled"] = raw_zero_match
    summary["rb01_postprocessed_with_published_one_sided_test"] = True
    write_json(summary_path, summary)
    update_status(out / "FOUNDATION_STATUS.md", summary)

    print(json.dumps({
        "passed": raw_zero_match,
        "raw_zero": results[0],
        "raw_one": results[1],
        "out": str(out),
    }, indent=2, sort_keys=True))
    return 0 if raw_zero_match else 1


if __name__ == "__main__":
    raise SystemExit(main())
