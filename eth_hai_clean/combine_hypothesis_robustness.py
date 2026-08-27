#!/usr/bin/env python3
"""Combine RB-06 through RB-17 aggregate outputs into one frozen stage summary."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, List


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_tsv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_tsv(path: Path, rows: List[Dict[str, object]], fieldnames: List[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--h1-h3", type=Path, required=True)
    parser.add_argument("--h4-trust", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    left = args.h1_h3.resolve()
    right = args.h4_trust.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    s1 = read_json(left / "h1_h3_robustness_summary.json")
    s2 = read_json(right / "h4_dke_trust_robustness_summary.json")
    checks = list(s1["checks"]) + list(s2["checks"])

    supplement = read_tsv(right / "rb07_h4_trust_multiplicity_supplement.tsv")
    supplement_changes = []
    for row in supplement:
        published = row.get("published_sig_0_0125", "False") == "True"
        holm = row.get("holm_sig_0_05", "False") == "True"
        bh = row.get("bh_fdr_sig_0_05", "False") == "True"
        if published != holm or published != bh:
            supplement_changes.append({
                "family": row.get("family"),
                "test_id": row.get("test_id"),
                "label": row.get("label"),
                "published_sig": published,
                "holm_sig": holm,
                "bh_sig": bh,
            })
    for index, check in enumerate(checks):
        if check["rb_id"] == "RB-07":
            check = dict(check)
            check["h4_trust_supplement_decision_changes"] = supplement_changes
            if supplement_changes:
                check["classification"] = "Specification-sensitive"
            checks[index] = check
            break

    order = ["RB-%02d" % value for value in range(6, 18)]
    by_id = {check["rb_id"]: check for check in checks}
    missing = sorted(set(order) - set(by_id))
    if missing:
        raise AssertionError("Missing checks: %s" % missing)
    checks = [by_id[rb_id] for rb_id in order]

    classifications = {check["rb_id"]: check["classification"] for check in checks}
    counts: Dict[str, int] = {}
    for value in classifications.values():
        counts[value] = counts.get(value, 0) + 1

    crosswalk = []
    for check in checks:
        crosswalk.append({
            "robustness_id": check["rb_id"],
            "concern": check["concern"],
            "classification": check["classification"],
            "interpretation": check.get("interpretation", ""),
        })

    summary = {
        "schema_version": "1.0",
        "stage": "hypothesis-specific robustness RB-06 through RB-17",
        "sample_n": 249,
        "passed": True,
        "checks_total": 12,
        "checks": checks,
        "classifications": classifications,
        "classification_counts": counts,
        "upstream_util_imported": False,
        "participant_level_data_emitted": False,
        "direct_reproduction_register_modified": False,
        "next_stage": "cross-cutting robustness RB-18 through RB-20",
    }
    write_json(out / "hypothesis_robustness_summary.json", summary)
    write_tsv(out / "hypothesis_robustness_crosswalk.tsv", crosswalk,
              ["robustness_id", "concern", "classification", "interpretation"])
    lines = [
        "# ETH HAI Hypothesis-Specific Robustness Gate",
        "",
        "- Overall execution: **PASS**",
        "- Checks completed: **12/12**",
        "- Direct reproduction register modified: **NO**",
        "- Upstream `util.py` imported: **NO**",
        "- Participant-level data emitted: **NO**",
        "",
    ]
    lines.extend("- %s: **%s**" % (check["rb_id"], check["classification"]) for check in checks)
    (out / "HYPOTHESIS_STATUS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "classifications": classifications}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
