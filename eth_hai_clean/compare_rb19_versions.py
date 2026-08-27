#!/usr/bin/env python3
"""Compare historical and modern RB-19 aggregate anchors."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Dict, List

from eth_hai_clean.hypothesis_common import write_json, write_tsv


def load(path: Path) -> Dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def as_float(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--historical", type=Path, required=True)
    parser.add_argument("--modern", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    historical = load(args.historical)
    modern = load(args.modern)
    hist_rows = {row["key"]: row for row in historical["anchors"]}
    modern_rows = {row["key"]: row for row in modern["anchors"]}
    if set(hist_rows) != set(modern_rows):
        raise AssertionError("Anchor key sets differ")

    rows: List[Dict[str, object]] = []
    decision_changes: List[Dict[str, object]] = []
    largest = []
    counts = {"Exact": 0, "Near": 0, "Difference": 0, "Non-numeric exact": 0}
    for key in sorted(hist_rows):
        left = hist_rows[key]
        right = modern_rows[key]
        hv = left["value"]
        mv = right["value"]
        hf = as_float(hv)
        mf = as_float(mv)
        alpha = left.get("alpha")
        if hf is not None and mf is not None:
            absolute = abs(hf - mf)
            scale = max(abs(hf), abs(mf), 1e-300)
            relative = absolute / scale
            if absolute <= 1e-12:
                classification = "Exact"
            elif absolute <= 1e-7 or relative <= 1e-7:
                classification = "Near"
            else:
                classification = "Difference"
            counts[classification] += 1
            hist_decision = None
            modern_decision = None
            decision_change = False
            if alpha not in (None, "") and left.get("quantity") == "p_value":
                threshold = float(alpha)
                hist_decision = bool(hf < threshold)
                modern_decision = bool(mf < threshold)
                decision_change = hist_decision != modern_decision
                if decision_change:
                    decision_changes.append({
                        "key": key,
                        "section": left["section"],
                        "alpha": threshold,
                        "historical_p": hf,
                        "modern_p": mf,
                    })
            row = {
                "key": key,
                "section": left["section"],
                "quantity": left["quantity"],
                "alpha": alpha,
                "historical_value": hf,
                "modern_value": mf,
                "absolute_difference": absolute,
                "relative_difference": relative,
                "classification": classification,
                "historical_decision": hist_decision,
                "modern_decision": modern_decision,
                "decision_change": decision_change,
            }
            largest.append((absolute, key))
        else:
            same = hv == mv
            classification = "Non-numeric exact" if same else "Difference"
            counts[classification] = counts.get(classification, 0) + 1
            row = {
                "key": key,
                "section": left["section"],
                "quantity": left["quantity"],
                "alpha": alpha,
                "historical_value": hv,
                "modern_value": mv,
                "absolute_difference": None,
                "relative_difference": None,
                "classification": classification,
                "historical_decision": None,
                "modern_decision": None,
                "decision_change": False,
            }
        rows.append(row)

    max_abs = max((float(row["absolute_difference"]) for row in rows if row["absolute_difference"] is not None), default=0.0)
    max_rel = max((float(row["relative_difference"]) for row in rows if row["relative_difference"] is not None), default=0.0)
    classification = "Specification-sensitive" if decision_changes else "Stable"
    memo = {
        "rb_id": "RB-19",
        "concern": "Precision and package sensitivity",
        "classification": classification,
        "historical_stack": historical["stack"],
        "modern_stack": modern["stack"],
        "anchors_compared_n": len(rows),
        "classification_counts": counts,
        "max_absolute_difference": max_abs,
        "max_relative_difference": max_rel,
        "decision_changes_n": len(decision_changes),
        "decision_changes": decision_changes,
        "interpretation": (
            "The historical frozen stack and current stable stack are compared on the same independently implemented "
            "aggregate anchors. Inferential stability is defined by decision agreement at each registered alpha; small "
            "floating-point differences without decision changes are not treated as substantive sensitivity."
        ),
    }
    summary = {
        "schema_version": "1.0",
        "stage": "RB-19 package-version sensitivity",
        "passed": True,
        "classification": classification,
        "memo": memo,
        "upstream_util_imported": False,
        "participant_level_data_emitted": False,
    }
    write_tsv(out / "rb19_cross_version_matrix.tsv", rows)
    write_json(out / "rb19_memo.json", memo)
    write_json(out / "rb19_summary.json", summary)
    (out / "RB19_STATUS.md").write_text(
        "# RB-19 Package-Version Sensitivity\n\n"
        "- Execution: **PASS**\n"
        "- Classification: **%s**\n"
        "- Anchors compared: **%d**\n"
        "- Decision changes: **%d**\n"
        "- Maximum absolute numerical difference: **%.12g**\n"
        "- Upstream `util.py` imported: **NO**\n"
        "- Participant-level data emitted: **NO**\n" % (
            classification, len(rows), len(decision_changes), max_abs
        ),
        encoding="utf-8",
    )
    print(json.dumps({"passed": True, "classification": classification, "decision_changes": len(decision_changes)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
