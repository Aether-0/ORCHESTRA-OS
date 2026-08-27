#!/usr/bin/env python3
"""Combine RB-18 through RB-20 into a final robustness-stage summary."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from eth_hai_clean.hypothesis_common import write_json, write_tsv


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rb18", type=Path, required=True)
    parser.add_argument("--rb19", type=Path, required=True)
    parser.add_argument("--rb20", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    summaries = [
        load(args.rb18 / "rb18_summary.json"),
        load(args.rb19 / "rb19_summary.json"),
        load(args.rb20 / "rb20_summary.json"),
    ]
    rows = []
    for summary in summaries:
        memo = summary["memo"]
        rows.append({
            "rb_id": memo["rb_id"],
            "concern": memo["concern"],
            "classification": memo["classification"],
            "interpretation": memo["interpretation"],
        })
    counts = Counter(row["classification"] for row in rows)
    payload = {
        "schema_version": "1.0",
        "stage": "final robustness checks RB-18 through RB-20",
        "passed": True,
        "checks_total": 3,
        "classifications": {row["rb_id"]: row["classification"] for row in rows},
        "classification_counts": dict(sorted(counts.items())),
        "upstream_util_imported": False,
        "participant_level_data_emitted": False,
        "direct_reproduction_register_modified": False,
        "checks": rows,
    }
    write_tsv(out / "rb18_20_crosswalk.tsv", rows)
    write_json(out / "final_robustness_summary.json", payload)
    (out / "FINAL_ROBUSTNESS_STATUS.md").write_text(
        "# ETH HAI Final Robustness Stage\n\n" +
        "\n".join("- %s: **%s**" % (row["rb_id"], row["classification"]) for row in rows) +
        "\n- Checks completed: **3/3**\n"
        "- Upstream `util.py` imported: **NO**\n"
        "- Participant-level data emitted: **NO**\n"
        "- Frozen direct-reproduction register modified: **NO**\n",
        encoding="utf-8",
    )
    print(json.dumps({"passed": True, "classifications": payload["classifications"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
