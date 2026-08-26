#!/usr/bin/env python3
"""Aggregate-only reproduction of the non-time portions of analysis_DKE_new.py.

This companion extractor preserves the released script's participant filter,
first-batch metrics, stable accuracy sort, ceil(25%) quartile size, and tests.
It intentionally omits completion-time analysis because demographic.csv is not
present in the pinned repository. It emits aggregates only: no participant rows
or identifiers.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
from scipy.stats import kruskal, mannwhitneyu

METRICS = [
    "accuracy",
    "agreement_fraction",
    "switching_fraction",
    "appropriate_reliance",
    "relative_positive_ai_reliance",
    "relative_positive_self_reliance",
]

PAPER_METRIC_NAMES = {
    "accuracy": "Accuracy (selection diagnostic)",
    "agreement_fraction": "Agreement Fraction",
    "switching_fraction": "Switch Fraction",
    "appropriate_reliance": "Accuracy-wid",
    "relative_positive_ai_reliance": "RAIR",
    "relative_positive_self_reliance": "RSR",
}


def write_tsv(path: Path, header: List[str], rows: List[List[object]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write("\t".join(header) + "\n")
        for row in rows:
            f.write("\t".join(str(x) for x in row) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    repo = args.repo.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    analysis_dir = repo / "data_analysis"
    sys.path.insert(0, str(analysis_dir))

    import util  # type: ignore

    util.data_folder = str(repo / "anonymous_data")
    filename = "all_valid_data.csv"
    valid_users, approved_users = util.find_valid_users(filename, 4)
    answer_dict = util.load_answers()
    user_question_order = util.get_user_question_order(filename, valid_users)
    usertask_dict = util.read_decisions(filename, valid_users)
    (
        self_assessment_first,
        self_assessment_second,
        other_assessment_first,
        other_assessment_second,
        survey_percentage_first,
        survey_percentage_second,
    ) = util.calc_miscalibration(filename, valid_users)

    records: List[Dict[str, object]] = []
    calibration_counts: Counter[str] = Counter()
    accuracy_counts: Counter[float] = Counter()

    for stable_index, user in enumerate(user_question_order):
        order = user_question_order[user]
        first_group = order[:6]
        (
            correct,
            agreement_fraction,
            switching_fraction,
            appropriate_reliance,
            initial_disagreement,
            rair,
            rsr,
        ) = util.calc_user_reliance_measures(
            user, usertask_dict, answer_dict, first_group
        )
        accuracy = correct / 6.0
        miscalibration = self_assessment_first[user] - correct
        if miscalibration > 0:
            calibration = "Overestimation"
        elif miscalibration < 0:
            calibration = "Underestimation"
        else:
            calibration = "Accurate"
        calibration_counts[calibration] += 1
        accuracy_counts[accuracy] += 1
        records.append(
            {
                "stable_index": stable_index,
                "accuracy": accuracy,
                "agreement_fraction": agreement_fraction,
                "switching_fraction": switching_fraction,
                "appropriate_reliance": appropriate_reliance,
                "relative_positive_ai_reliance": rair,
                "relative_positive_self_reliance": rsr,
                "calibration": calibration,
            }
        )

    # Matches the released code: Python's stable descending sort by first-batch accuracy.
    ranked = sorted(records, key=lambda row: row["accuracy"], reverse=True)
    quartile_n = math.ceil(len(ranked) * 0.25)
    top = ranked[:quartile_n]
    bottom = ranked[-quartile_n:]

    def composition(group: List[Dict[str, object]]) -> Dict[str, int]:
        c = Counter(str(row["calibration"]) for row in group)
        return {
            "Underestimation": c["Underestimation"],
            "Accurate": c["Accurate"],
            "Overestimation": c["Overestimation"],
        }

    top_comp = composition(top)
    bottom_comp = composition(bottom)

    top_cutoff = float(top[-1]["accuracy"])
    bottom_cutoff = float(bottom[0]["accuracy"])
    top_cutoff_total = sum(float(r["accuracy"]) == top_cutoff for r in ranked)
    top_cutoff_selected = sum(float(r["accuracy"]) == top_cutoff for r in top)
    bottom_cutoff_total = sum(float(r["accuracy"]) == bottom_cutoff for r in ranked)
    bottom_cutoff_selected = sum(float(r["accuracy"]) == bottom_cutoff for r in bottom)

    result_rows: List[List[object]] = []
    result_json: Dict[str, object] = {}
    for metric in METRICS:
        top_values = np.asarray([float(row[metric]) for row in top], dtype=float)
        bottom_values = np.asarray([float(row[metric]) for row in bottom], dtype=float)
        h, p = kruskal(top_values, bottom_values)
        u_greater, p_greater = mannwhitneyu(
            top_values, bottom_values, alternative="greater"
        )
        result_rows.append(
            [
                metric,
                PAPER_METRIC_NAMES[metric],
                quartile_n,
                float(np.mean(top_values)),
                float(np.std(top_values)),
                float(np.mean(bottom_values)),
                float(np.std(bottom_values)),
                float(h),
                float(p),
                float(u_greater),
                float(p_greater),
                bool(p < 0.0125),
            ]
        )
        result_json[metric] = {
            "label": PAPER_METRIC_NAMES[metric],
            "n_top": quartile_n,
            "n_bottom": quartile_n,
            "top_mean": float(np.mean(top_values)),
            "top_sd_ddof0": float(np.std(top_values)),
            "bottom_mean": float(np.mean(bottom_values)),
            "bottom_sd_ddof0": float(np.std(bottom_values)),
            "kruskal_h": float(h),
            "kruskal_p": float(p),
            "mannwhitney_u_greater": float(u_greater),
            "mannwhitney_p_greater": float(p_greater),
            "passes_released_alpha_0_0125": bool(p < 0.0125),
        }

    summary = {
        "schema_version": "1.0",
        "upstream_repository": "RichardHGL/CHI2023_DKE",
        "upstream_commit": "008f9833ab8c4c23ed94908e0108053a2240a100",
        "source_script": "data_analysis/analysis_DKE_new.py",
        "participant_count": len(ranked),
        "valid_user_count": len(valid_users),
        "approved_user_count": len(approved_users),
        "quartile_rule": "ceil(N * 0.25)",
        "quartile_n": quartile_n,
        "ranking_rule": "stable descending sort by first-batch accuracy",
        "calibration_counts": dict(calibration_counts),
        "top_quartile_composition": top_comp,
        "bottom_quartile_composition": bottom_comp,
        "top_overestimation_percent": 100.0 * top_comp["Overestimation"] / quartile_n,
        "bottom_overestimation_percent": 100.0 * bottom_comp["Overestimation"] / quartile_n,
        "accuracy_distribution": {
            f"{score:.12g}": count
            for score, count in sorted(accuracy_counts.items(), reverse=True)
        },
        "tie_audit": {
            "top_cutoff_accuracy": top_cutoff,
            "top_cutoff_total_participants": top_cutoff_total,
            "top_cutoff_selected_participants": top_cutoff_selected,
            "top_cutoff_splits_tie": top_cutoff_selected < top_cutoff_total,
            "bottom_cutoff_accuracy": bottom_cutoff,
            "bottom_cutoff_total_participants": bottom_cutoff_total,
            "bottom_cutoff_selected_participants": bottom_cutoff_selected,
            "bottom_cutoff_splits_tie": bottom_cutoff_selected < bottom_cutoff_total,
        },
        "completion_time_component": {
            "status": "not_testable",
            "reason": "anonymous_data/demographic.csv is absent from the pinned repository",
        },
        "results": result_json,
        "participant_level_data_emitted": False,
        "participant_identifiers_emitted": False,
        "upstream_source_modified": False,
    }

    write_tsv(
        out / "dke_table8_and_diagnostic_results.tsv",
        [
            "metric",
            "paper_label",
            "n_per_quartile",
            "top_mean",
            "top_sd_ddof0",
            "bottom_mean",
            "bottom_sd_ddof0",
            "kruskal_h",
            "kruskal_p",
            "mannwhitney_u_greater",
            "mannwhitney_p_greater",
            "passes_alpha_0_0125",
        ],
        result_rows,
    )
    write_tsv(
        out / "dke_quartile_composition.tsv",
        ["quartile", "n", "underestimation", "accurate", "overestimation", "overestimation_percent"],
        [
            ["Top", quartile_n, top_comp["Underestimation"], top_comp["Accurate"], top_comp["Overestimation"], 100.0 * top_comp["Overestimation"] / quartile_n],
            ["Bottom", quartile_n, bottom_comp["Underestimation"], bottom_comp["Accurate"], bottom_comp["Overestimation"], 100.0 * bottom_comp["Overestimation"] / quartile_n],
        ],
    )
    write_tsv(
        out / "dke_accuracy_distribution.tsv",
        ["first_batch_accuracy", "participant_count"],
        [[score, count] for score, count in sorted(accuracy_counts.items(), reverse=True)],
    )
    (out / "dke_non_time_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out / "STATUS.md").write_text(
        "# DKE non-time aggregate extraction\n\n"
        f"- Participants: **{len(ranked)}**\n"
        f"- Quartile size: **{quartile_n}**\n"
        f"- Overestimators: **{calibration_counts['Overestimation']}**\n"
        f"- Top composition: **{top_comp}**\n"
        f"- Bottom composition: **{bottom_comp}**\n"
        f"- Top cutoff tie split: **{top_cutoff_selected < top_cutoff_total}**\n"
        f"- Bottom cutoff tie split: **{bottom_cutoff_selected < bottom_cutoff_total}**\n"
        "- Completion time: **NOT TESTABLE; demographic.csv absent**\n"
        "- Participant-level rows or identifiers emitted: **NO**\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "participant_count": len(ranked),
        "quartile_n": quartile_n,
        "calibration_counts": dict(calibration_counts),
        "top_composition": top_comp,
        "bottom_composition": bottom_comp,
        "tie_audit": summary["tie_audit"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
