#!/usr/bin/env python3
"""Aggregate-only companion extraction for Section 5.4 trust results.

This script mirrors the released analysis_trust_new.py computations while emitting
only aggregate statistics. It does not emit participant identifiers or rows.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
from pingouin import ancova
from scipy.stats import spearmanr, wilcoxon

from util import (
    UserPerformance,
    calc_ATI_scale,
    calc_miscalibration,
    calc_propensity_to_trust,
    calc_trust_in_automation,
    calc_user_reliance_measures,
    check_user_condition,
    find_valid_users,
    get_user_conditions,
    get_user_question_order,
    load_answers,
    read_decisions,
)


def build_performance(user_question_order, usertask_dict, answer_dict, self_first, self_second):
    user_mis_first = {}
    user_mis_second = {}
    user2performance = {}
    for user in user_question_order:
        order = user_question_order[user]
        first_group = order[:6]
        second_group = order[-6:]
        perf = UserPerformance(username=user, question_order=order)

        for label, group, self_assessment in (
            ("first_group", first_group, self_first[user]),
            ("second_group", second_group, self_second[user]),
        ):
            correct, agreement, switching, appropriate, _, rair, rsr = calc_user_reliance_measures(
                user, usertask_dict, answer_dict, group
            )
            perf.add_performance(
                accuracy=correct / 6.0,
                agreement_fraction=agreement,
                switching_fraction=switching,
                appropriate_reliance=appropriate,
                relative_positive_ai_reliance=rair,
                relative_positive_self_reliance=rsr,
                group=label,
            )
            perf.add_miscalibration(
                self_assessment=self_assessment,
                actual_correct_number=correct,
                group=label,
            )

        correct, agreement, switching, appropriate, _, rair, rsr = calc_user_reliance_measures(
            user, usertask_dict, answer_dict, first_group + second_group
        )
        perf.add_performance(
            accuracy=correct / 12.0,
            agreement_fraction=agreement,
            switching_fraction=switching,
            appropriate_reliance=appropriate,
            relative_positive_ai_reliance=rair,
            relative_positive_self_reliance=rsr,
            group="overall",
        )
        user_mis_first[user] = perf.miscalibration["first_group"]
        user_mis_second[user] = perf.miscalibration["second_group"]
        user2performance[user] = perf
    return user_mis_first, user_mis_second, user2performance


def ancova_records(df: pd.DataFrame, between: str):
    result = ancova(
        data=df,
        dv="TiA-Trust",
        covar=["ATI", "TiA-Propensity"],
        between=between,
        effsize="n2",
    )
    rows = []
    for _, row in result.iterrows():
        rows.append(
            {
                "source": str(row["Source"]),
                "SS": None if pd.isna(row["SS"]) else float(row["SS"]),
                "DF": None if pd.isna(row["DF"]) else int(row["DF"]),
                "F": None if pd.isna(row["F"]) else float(row["F"]),
                "p_unc": None if pd.isna(row["p-unc"]) else float(row["p-unc"]),
                "n2": None if pd.isna(row["n2"]) else float(row["n2"]),
            }
        )
    return rows


def main() -> int:
    out_dir = Path(os.environ["TRUST_EXTRACT_OUTPUT_DIR"])
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = "all_valid_data.csv"

    valid_users, _ = find_valid_users(filename, 4)
    condition_dict = get_user_conditions(filename, valid_users)
    answer_dict = load_answers()
    question_order = get_user_question_order(filename, valid_users)
    decisions = read_decisions(filename, valid_users)
    self_first, self_second, *_ = calc_miscalibration(filename, valid_users)
    trust_first, trust_second = calc_trust_in_automation(filename, valid_users)
    ati = calc_ATI_scale(filename, valid_users)
    propensity = calc_propensity_to_trust(filename, valid_users)
    mis_first, mis_second, user2performance = build_performance(
        question_order, decisions, answer_dict, self_first, self_second
    )

    tutorial_users = sorted(
        condition_dict["with tutorial, no xai"] | condition_dict["with tutorial, with xai"]
    )
    before = np.asarray([trust_first[u] for u in tutorial_users], dtype=float)
    after = np.asarray([trust_second[u] for u in tutorial_users], dtype=float)
    w = wilcoxon(before, after)

    records = []
    for user in trust_first:
        if mis_first[user] > 0:
            group = "Overestimation"
        elif mis_first[user] < 0:
            group = "Underestimation"
        else:
            group = "Accurate"
        overall = user2performance[user].performance["overall"]
        records.append(
            {
                "miscalibration": group,
                "condition": check_user_condition(user, condition_dict),
                "ATI": ati[user],
                "TiA-Propensity": propensity[user],
                "TiA-Trust": (trust_first[user] + trust_second[user]) / 2.0,
                "accuracy": overall["accuracy"],
                "agreement_fraction": overall["agreement_fraction"],
                "switching_fraction": overall["switching_fraction"],
                "RAIR": overall["relative_positive_ai_reliance"],
                "RSR": overall["relative_positive_self_reliance"],
            }
        )
    df = pd.DataFrame.from_records(records)

    correlations = []
    for variable in ["TiA-Trust", "accuracy", "agreement_fraction", "switching_fraction", "RAIR", "RSR"]:
        rho, p = spearmanr(df["TiA-Propensity"], df[variable])
        correlations.append(
            {
                "x": "TiA-Propensity",
                "y": variable,
                "rho": float(rho),
                "p_value": float(p),
                "n": int(len(df)),
            }
        )

    output = {
        "schema_version": "1.0",
        "sample_n": int(len(df)),
        "tutorial_n": int(len(tutorial_users)),
        "trust_wilcoxon": {
            "statistic": float(w.statistic),
            "p_value": float(w.pvalue),
            "before_mean": float(np.mean(before)),
            "after_mean": float(np.mean(after)),
            "before_sd_population": float(np.std(before)),
            "after_sd_population": float(np.std(after)),
        },
        "ancova_miscalibration": ancova_records(df, "miscalibration"),
        "ancova_condition": ancova_records(df, "condition"),
        "correlations": correlations,
        "participant_level_data_emitted": False,
    }
    (out_dir / "trust_aggregate_results.json").write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    with (out_dir / "trust_correlations.tsv").open("w", encoding="utf-8", newline="\n") as f:
        f.write("x\ty\trho\tp_value\tn\n")
        for row in correlations:
            f.write(f"{row['x']}\t{row['y']}\t{row['rho']:.17g}\t{row['p_value']:.17g}\t{row['n']}\n")

    with (out_dir / "trust_ancova.tsv").open("w", encoding="utf-8", newline="\n") as f:
        f.write("model\tsource\tSS\tDF\tF\tp_unc\tn2\n")
        for model, rows in (("miscalibration", output["ancova_miscalibration"]), ("condition", output["ancova_condition"])):
            for row in rows:
                f.write(
                    "\t".join(
                        [
                            model,
                            row["source"],
                            "" if row["SS"] is None else f"{row['SS']:.17g}",
                            "" if row["DF"] is None else str(row["DF"]),
                            "" if row["F"] is None else f"{row['F']:.17g}",
                            "" if row["p_unc"] is None else f"{row['p_unc']:.17g}",
                            "" if row["n2"] is None else f"{row['n2']:.17g}",
                        ]
                    )
                    + "\n"
                )

    print(json.dumps({"sample_n": len(df), "tutorial_n": len(tutorial_users), "correlation_rows": len(correlations)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
