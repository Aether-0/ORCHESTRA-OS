#!/usr/bin/env python3
"""Extract aggregate H3 correlation rows from the released analysis specification.

This companion extractor mirrors the correlation block in analysis_H3_new.py. It emits
only aggregate statistics and never writes participant identifiers or participant rows.
The upstream source checkout is not modified.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from pingouin import pairwise_corr

from util import (
    UserPerformance,
    calc_miscalibration,
    calc_trust_in_automation,
    calc_user_reliance_measures,
    find_valid_users,
    get_user_conditions,
    get_user_question_order,
    load_answers,
    read_decisions,
)


def collect(mode, users, user_question_order, usertask_dict, answer_dict,
            self_assessment_first, self_assessment_second):
    assert mode in {"underestimation", "overestimation"}
    diff = {
        "miscalibration": [],
        "accuracy": [],
        "appropriate_reliance": [],
        "relative_positive_ai_reliance": [],
        "relative_positive_self_reliance": [],
    }

    for user in users:
        order = user_question_order[user]
        first_group = order[:6]
        second_group = order[-6:]

        perf = UserPerformance(username=user, question_order=order)
        c1, _, _, ar1, _, rair1, rsr1 = calc_user_reliance_measures(
            user, usertask_dict, answer_dict, first_group
        )
        perf.add_miscalibration(self_assessment_first[user], c1, "first_group")
        m1 = perf.miscalibration["first_group"]

        if mode == "underestimation" and m1 >= 0:
            continue
        if mode == "overestimation" and m1 <= 0:
            continue

        c2, _, _, ar2, _, rair2, rsr2 = calc_user_reliance_measures(
            user, usertask_dict, answer_dict, second_group
        )
        perf.add_miscalibration(self_assessment_second[user], c2, "second_group")
        m2 = perf.miscalibration["second_group"]

        diff["miscalibration"].append(m2 - m1)
        diff["accuracy"].append(c2 / 6.0 - c1 / 6.0)
        diff["appropriate_reliance"].append(ar2 - ar1)
        diff["relative_positive_ai_reliance"].append(rair2 - rair1)
        diff["relative_positive_self_reliance"].append(rsr2 - rsr1)

    frame = pd.DataFrame(diff)
    result = pairwise_corr(
        frame,
        columns=["miscalibration"],
        method="spearman",
        alternative="less",
        padjust="bonf",
    )
    result.insert(0, "group", mode)
    return frame, result


def main():
    output_dir = Path(__import__("os").environ["H3_EXTRACT_OUTPUT_DIR"])
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = "all_valid_data.csv"
    valid_users, _ = find_valid_users(filename, 4)
    user_condition_dict = get_user_conditions(filename, valid_users)
    answer_dict = load_answers()
    user_question_order = get_user_question_order(filename, valid_users)
    usertask_dict = read_decisions(filename, valid_users)
    calc_trust_in_automation(filename, valid_users)  # Preserve original load path.
    (self_assessment_first, self_assessment_second, _, _, _, _) = calc_miscalibration(
        filename, valid_users
    )

    tutorial_users = (
        user_condition_dict["with tutorial, no xai"]
        | user_condition_dict["with tutorial, with xai"]
    )

    all_results = []
    group_sizes = {}
    for mode in ["underestimation", "overestimation"]:
        frame, result = collect(
            mode,
            tutorial_users,
            user_question_order,
            usertask_dict,
            answer_dict,
            self_assessment_first,
            self_assessment_second,
        )
        group_sizes[mode] = int(len(frame))
        all_results.append(result)

    combined = pd.concat(all_results, ignore_index=True)
    combined.to_csv(output_dir / "h3_correlations_unrounded.tsv", sep="\t", index=False)
    combined.round(3).to_csv(output_dir / "h3_correlations_rounded.tsv", sep="\t", index=False)
    (output_dir / "h3_correlations_unrounded.json").write_text(
        combined.to_json(orient="records", indent=2) + "\n", encoding="utf-8"
    )

    summary = {
        "schema_version": "1.0",
        "upstream_script_specification": "analysis_H3_new.py correlation block",
        "group_sizes": group_sizes,
        "method": "spearman",
        "alternative": "less",
        "padjust": "bonf",
        "participant_level_data_emitted": False,
        "participant_identifiers_emitted": False,
        "rows": json.loads(combined.to_json(orient="records")),
    }
    (output_dir / "h3_correlation_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(combined.round(6).to_string(index=False))
    print(json.dumps({"group_sizes": group_sizes, "rows": len(combined)}, sort_keys=True))


if __name__ == "__main__":
    main()
