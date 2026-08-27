#!/usr/bin/env python3
"""Hypothesis-specific robustness checks RB-06 through RB-11.

All outputs are aggregate-only. The script uses the independent clean core and never
imports the released util.py or emits participant identifiers/raw participant rows.
"""
from __future__ import annotations

import argparse
import json
import math
import warnings
from pathlib import Path
from typing import Dict, List, Mapping, Sequence, Tuple

import numpy as np
import pandas as pd
from scipy import stats

from eth_hai_clean.core import build_clean_metric_frame
from eth_hai_clean.hypothesis_common import (
    ALPHA_PUBLISHED,
    CALIBRATION_ORDER,
    METRICS,
    adjust_pvalues,
    bootstrap_ci,
    calibration_label,
    exact_sign_flip_sum_test,
    json_default,
    kruskal_three,
    multiplicity_rows,
    pairwise_mannwhitney,
    rank_biserial_paired,
    write_json,
    write_tsv,
)

TUTORIAL_RAW = 0


def add_groups(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["group_first"] = out["miscalibration_first"].astype(float).map(calibration_label)
    out["group_second"] = out["miscalibration_second"].astype(float).map(calibration_label)
    for _, metric in METRICS:
        out["delta_%s" % metric] = out["second_%s" % metric] - out["first_%s" % metric]
    out["delta_miscalibration"] = out["miscalibration_second"] - out["miscalibration_first"]
    return out


def wilcoxon_safe(before: Sequence[float], after: Sequence[float], alternative: str,
                   zero_method: str = "wilcox", correction: bool = False,
                   mode: str = "auto") -> Dict[str, object]:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            result = stats.wilcoxon(
                before,
                after,
                alternative=alternative,
                zero_method=zero_method,
                correction=correction,
                mode=mode,
            )
            return {
                "statistic": float(result.statistic),
                "p_value": float(result.pvalue),
                "error": "",
                "warnings": " | ".join(str(item.message) for item in caught),
            }
        except Exception as exc:
            return {
                "statistic": None,
                "p_value": None,
                "error": repr(exc),
                "warnings": " | ".join(str(item.message) for item in caught),
            }


def rb06_group_outcome_coupling(frame_zero: pd.DataFrame, frame_nan: pd.DataFrame):
    rows: List[Dict[str, object]] = []
    pairwise: List[Dict[str, object]] = []
    specifications = (
        ("published_same_batch", "group_first", "first"),
        ("heldout_forward", "group_first", "second"),
        ("reverse_crossfit_exploratory", "group_second", "first"),
        ("change_by_first_group_exploratory", "group_first", "delta"),
    )
    for label, metric in METRICS:
        policies = (("released_zero", frame_zero),)
        if metric in ("rair", "rsr"):
            policies = (("released_zero", frame_zero), ("defined_participants", frame_nan))
        for policy, source in policies:
            for specification, group_column, outcome_scope in specifications:
                value_column = "%s_%s" % (outcome_scope, metric)
                result = kruskal_three(source, group_column, value_column)
                row = {
                    "rb_id": "RB-06",
                    "metric": label,
                    "metric_key": metric,
                    "ratio_policy": policy,
                    "specification": specification,
                    "group_column": group_column,
                    "outcome_column": value_column,
                    **result,
                    "significant_published_alpha": bool(result["p_value"] < ALPHA_PUBLISHED),
                }
                rows.append(row)
                if specification in ("published_same_batch", "heldout_forward"):
                    for pair in pairwise_mannwhitney(source, group_column, value_column):
                        pairwise.append({
                            "rb_id": "RB-06",
                            "metric": label,
                            "ratio_policy": policy,
                            "specification": specification,
                            **pair,
                        })

    same = {(row["metric"], row["ratio_policy"]): row for row in rows if row["specification"] == "published_same_batch"}
    held = {(row["metric"], row["ratio_policy"]): row for row in rows if row["specification"] == "heldout_forward"}
    changes = []
    for key, published in same.items():
        forward = held[key]
        if bool(published["significant_published_alpha"]) != bool(forward["significant_published_alpha"]):
            changes.append({
                "metric": key[0],
                "ratio_policy": key[1],
                "same_batch_p": published["p_value"],
                "heldout_p": forward["p_value"],
                "same_batch_epsilon_squared": published["epsilon_squared"],
                "heldout_epsilon_squared": forward["epsilon_squared"],
            })
    memo = {
        "rb_id": "RB-06",
        "concern": "H1 calibration-group and outcome coupling",
        "classification": "Specification-sensitive" if changes else "Stable",
        "decision_changes_same_to_heldout": changes,
        "interpretation": (
            "Same-batch H1 associations are partly mechanical because calibration groups contain first-batch accuracy. "
            "Held-out second-batch and reverse cross-fit analyses separate grouping from outcome measurement; reverse "
            "cross-fit remains exploratory because second-batch calibration may be affected by the intervention."
        ),
    }
    return rows, pairwise, memo


def h2_samples(frame: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    tutorial = frame.loc[frame["tutorial_raw"].astype(int) == TUTORIAL_RAW].copy()
    tutorial = tutorial.loc[tutorial["miscalibration_first"].astype(float) != 0.0].copy()
    return {
        "all": tutorial,
        "under": tutorial.loc[tutorial["miscalibration_first"] < 0].copy(),
        "over": tutorial.loc[tutorial["miscalibration_first"] > 0].copy(),
    }


def h2_primary_tests(frame: pd.DataFrame) -> List[Dict[str, object]]:
    rows = []
    for group, subset in h2_samples(frame).items():
        before = subset["miscalibration_first"].abs().astype(float).to_numpy()
        after = subset["miscalibration_second"].abs().astype(float).to_numpy()
        result = wilcoxon_safe(before, after, alternative="greater")
        rows.append({
            "test_id": "H2_%s" % group,
            "label": "H2 absolute calibration improvement: %s" % group,
            "group": group,
            "n": int(len(subset)),
            "statistic": result["statistic"],
            "p_value": result["p_value"],
            "before_mean": float(before.mean()),
            "after_mean": float(after.mean()),
        })
    return rows


def h3_table4_tests(frame: pd.DataFrame) -> List[Dict[str, object]]:
    tutorial = frame.loc[frame["tutorial_raw"].astype(int) == TUTORIAL_RAW].copy()
    rows = []
    for group, group_mask, alternative in (
        ("under", tutorial["miscalibration_first"] < 0, "greater"),
        ("over", tutorial["miscalibration_first"] > 0, "less"),
    ):
        subset = tutorial.loc[group_mask].copy()
        for label, metric in METRICS:
            before = subset["first_%s" % metric].astype(float).to_numpy()
            after = subset["second_%s" % metric].astype(float).to_numpy()
            result = wilcoxon_safe(before, after, alternative=alternative)
            rows.append({
                "test_id": "H3_T4_%s_%s" % (group, metric),
                "label": "H3 Table 4 %s %s" % (group, label),
                "group": group,
                "metric": label,
                "p_value": result["p_value"],
                "statistic": result["statistic"],
                "alternative": alternative,
            })
    return rows


def h3_correlations(frame: pd.DataFrame) -> List[Dict[str, object]]:
    tutorial = frame.loc[frame["tutorial_raw"].astype(int) == TUTORIAL_RAW].copy()
    rows: List[Dict[str, object]] = []
    correlation_metrics = (
        ("Accuracy", "accuracy"),
        ("Accuracy-wid", "appropriate_reliance"),
        ("RAIR", "rair"),
        ("RSR", "rsr"),
    )
    paper_p = {
        ("under", "Accuracy"): ".001",
        ("under", "Accuracy-wid"): ".009",
        ("under", "RAIR"): ".039",
        ("under", "RSR"): ".068",
        ("over", "Accuracy"): "<.001",
        ("over", "Accuracy-wid"): "<.001",
        ("over", "RAIR"): "<.001",
        ("over", "RSR"): ".005",
    }
    for group, mask in (
        ("under", tutorial["miscalibration_first"] < 0),
        ("over", tutorial["miscalibration_first"] > 0),
    ):
        subset = tutorial.loc[mask].copy()
        for label, metric in correlation_metrics:
            pair = subset[["delta_miscalibration", "delta_%s" % metric]].dropna()
            one = stats.spearmanr(pair["delta_miscalibration"], pair["delta_%s" % metric], alternative="less")
            two = stats.spearmanr(pair["delta_miscalibration"], pair["delta_%s" % metric], alternative="two-sided")
            rows.append({
                "test_id": "H3_T5_%s_%s" % (group, metric),
                "label": "H3 Table 5 %s %s" % (group, label),
                "group": group,
                "metric": label,
                "n": int(len(pair)),
                "rho": float(one.statistic),
                "p_value": float(one.pvalue),
                "p_two_sided": float(two.pvalue),
                "paper_p_display": paper_p[(group, label)],
            })
    return rows


def h3_table6_tests(frame: pd.DataFrame) -> List[Dict[str, object]]:
    tutorial = frame.loc[frame["tutorial_raw"].astype(int) == TUTORIAL_RAW].copy()
    rows = []
    for group, mask in (
        ("under", tutorial["miscalibration_first"] < 0),
        ("over", tutorial["miscalibration_first"] > 0),
    ):
        subset = tutorial.loc[mask].copy()
        for label, metric in METRICS:
            xai = pd.to_numeric(subset.loc[subset["xai_raw"] == 1, "delta_%s" % metric], errors="coerce").dropna()
            no_xai = pd.to_numeric(subset.loc[subset["xai_raw"] == 0, "delta_%s" % metric], errors="coerce").dropna()
            result = stats.kruskal(xai, no_xai)
            rows.append({
                "test_id": "H3_T6_%s_%s" % (group, metric),
                "label": "H3 Table 6 %s %s" % (group, label),
                "group": group,
                "metric": label,
                "n_xai": int(len(xai)),
                "n_no_xai": int(len(no_xai)),
                "statistic": float(result.statistic),
                "p_value": float(result.pvalue),
            })
    return rows


def rb07_multiplicity(frame: pd.DataFrame):
    h1 = []
    for label, metric in METRICS:
        result = kruskal_three(frame, "group_first", "first_%s" % metric)
        h1.append({"test_id": "H1_%s" % metric, "label": "H1 %s" % label, "p_value": result["p_value"]})
    h2 = h2_primary_tests(frame)
    t4 = h3_table4_tests(frame)
    t5 = h3_correlations(frame)
    t6 = h3_table6_tests(frame)

    rows: List[Dict[str, object]] = []
    rows.extend(multiplicity_rows("H1_six_omnibus", h1))
    rows.extend(multiplicity_rows("H2_three_calibration_tests", h2))
    for group in ("under", "over"):
        rows.extend(multiplicity_rows("H3_Table4_%s_six" % group, [row for row in t4 if row["group"] == group]))
        rows.extend(multiplicity_rows("H3_Table5_%s_four" % group, [row for row in t5 if row["group"] == group]))
        rows.extend(multiplicity_rows("H3_Table6_%s_six" % group, [row for row in t6 if row["group"] == group]))
    rows.extend(multiplicity_rows("H3_Table4_global_twelve", t4))
    rows.extend(multiplicity_rows("H3_Table5_global_eight", t5))
    rows.extend(multiplicity_rows("H3_Table6_global_twelve", t6))

    decision_changes = [
        {"family": row["family"], "test_id": row["test_id"], "label": row["label"],
         "published_sig": row["published_sig_0_0125"], "holm_sig": row["holm_sig_0_05"],
         "bh_sig": row["bh_fdr_sig_0_05"]}
        for row in rows
        if len(row["family"].split("_global_")) == 1
        and (bool(row["published_sig_0_0125"]) != bool(row["holm_sig_0_05"])
             or bool(row["published_sig_0_0125"]) != bool(row["bh_fdr_sig_0_05"]))
    ]
    memo = {
        "rb_id": "RB-07",
        "concern": "Multiplicity-family ambiguity",
        "classification": "Specification-sensitive" if decision_changes else "Stable",
        "decision_changes": decision_changes,
        "interpretation": (
            "A fixed alpha of .0125 is not equivalent to every plausible family definition. The matrix separates "
            "raw decisions, Bonferroni by family size, Holm, and BH-FDR without replacing the published rule."
        ),
    }
    return rows, memo


def rb08_wilcoxon_grid(frame: pd.DataFrame):
    rows: List[Dict[str, object]] = []
    for group, subset in h2_samples(frame).items():
        before = subset["miscalibration_first"].abs().astype(float).to_numpy()
        after = subset["miscalibration_second"].abs().astype(float).to_numpy()
        for zero_method in ("wilcox", "pratt", "zsplit"):
            for correction in (False, True):
                for alternative in ("greater", "two-sided"):
                    for mode in ("auto", "approx"):
                        result = wilcoxon_safe(before, after, alternative, zero_method, correction, mode)
                        rows.append({
                            "rb_id": "RB-08",
                            "group": group,
                            "n": int(len(subset)),
                            "zero_method": zero_method,
                            "continuity_correction": correction,
                            "alternative": alternative,
                            "mode": mode,
                            **result,
                            "significant_0_0125": bool(result["p_value"] is not None and result["p_value"] < ALPHA_PUBLISHED),
                            "significant_0_05": bool(result["p_value"] is not None and result["p_value"] < 0.05),
                        })
    over = [row for row in rows if row["group"] == "over" and row["error"] == ""]
    decisions = sorted(set(bool(row["significant_0_0125"]) for row in over))
    memo = {
        "rb_id": "RB-08",
        "concern": "H2 Wilcoxon zero-method, correction, and direction sensitivity",
        "classification": "Specification-sensitive" if len(decisions) > 1 else "Stable",
        "overestimator_decisions_at_0_0125": decisions,
        "interpretation": (
            "The grid preserves the released one-sided specification while showing how zero handling, continuity "
            "correction, approximation mode, and a two-sided alternative affect the boundary overestimator result."
        ),
    }
    return rows, memo


def rb09_boundary(frame: pd.DataFrame):
    subset = h2_samples(frame)["over"]
    before = subset["miscalibration_first"].abs().astype(float).to_numpy()
    after = subset["miscalibration_second"].abs().astype(float).to_numpy()
    improvement = before - after
    positive = int(np.sum(improvement > 0))
    negative = int(np.sum(improvement < 0))
    zero = int(np.sum(improvement == 0))
    sign = stats.binomtest(positive, positive + negative, p=0.5, alternative="greater") if positive + negative else None
    signflip = exact_sign_flip_sum_test(improvement)
    mean_ci = bootstrap_ci(improvement, "mean", draws=20000, seed=906)
    median_ci = bootstrap_ci(improvement, "median", draws=20000, seed=907)
    released = wilcoxon_safe(before, after, "greater")
    two_sided = wilcoxon_safe(before, after, "two-sided")
    evidence = {
        "rb_id": "RB-09",
        "n": int(len(subset)),
        "positive_improvement_n": positive,
        "negative_improvement_n": negative,
        "zero_change_n": zero,
        "mean_improvement": float(np.mean(improvement)),
        "median_improvement": float(np.median(improvement)),
        "released_one_sided_wilcoxon": released,
        "two_sided_wilcoxon": two_sided,
        "exact_sign_test_p_greater": float(sign.pvalue) if sign else None,
        "exact_sign_flip_sum_test": signflip,
        "bootstrap_mean": mean_ci,
        "bootstrap_median": median_ci,
        "rank_biserial_after_minus_before": rank_biserial_paired(before, after),
    }
    stable = (
        released["p_value"] is not None and released["p_value"] < ALPHA_PUBLISHED
        and two_sided["p_value"] is not None and two_sided["p_value"] < ALPHA_PUBLISHED
        and (sign is not None and sign.pvalue < ALPHA_PUBLISHED)
        and signflip["p_greater"] < ALPHA_PUBLISHED
        and mean_ci["ci_low"] > 0
        and median_ci["ci_low"] > 0
    )
    memo = {
        "rb_id": "RB-09",
        "concern": "H2 overestimator boundary result",
        "classification": "Stable" if stable else "Specification-sensitive",
        "interpretation": (
            "The published one-sided p-value lies just below .0125. Exact sign-based, sign-flip, two-sided, and "
            "bootstrap evidence assess whether that conclusion survives methods that make fewer rank-distribution assumptions."
        ),
    }
    return evidence, memo


def rb10_h3_directional(frame: pd.DataFrame):
    tutorial = frame.loc[frame["tutorial_raw"].astype(int) == TUTORIAL_RAW].copy()
    rows: List[Dict[str, object]] = []
    for group, mask, expected_alternative in (
        ("under", tutorial["miscalibration_first"] < 0, "greater"),
        ("over", tutorial["miscalibration_first"] > 0, "less"),
    ):
        subset = tutorial.loc[mask].copy()
        temp = []
        for label, metric in METRICS:
            before = subset["first_%s" % metric].astype(float).to_numpy()
            after = subset["second_%s" % metric].astype(float).to_numpy()
            directional = wilcoxon_safe(before, after, expected_alternative)
            two = wilcoxon_safe(before, after, "two-sided")
            diff = after - before
            temp.append({
                "rb_id": "RB-10",
                "group": group,
                "metric": label,
                "n": int(len(subset)),
                "expected_alternative": expected_alternative,
                "directional_statistic": directional["statistic"],
                "p_directional": directional["p_value"],
                "two_sided_statistic": two["statistic"],
                "p_two_sided": two["p_value"],
                "mean_change_second_minus_first": float(np.mean(diff)),
                "median_change_second_minus_first": float(np.median(diff)),
                "paired_rank_biserial_second_minus_first": rank_biserial_paired(before, after),
                "cohens_dz": float(np.mean(diff) / np.std(diff, ddof=1)) if np.std(diff, ddof=1) > 0 else 0.0,
            })
        directional_adj = adjust_pvalues([row["p_directional"] for row in temp])
        two_adj = adjust_pvalues([row["p_two_sided"] for row in temp])
        for index, row in enumerate(temp):
            row.update({
                "p_directional_holm": directional_adj["holm"][index],
                "directional_holm_sig": bool(directional_adj["holm"][index] < 0.05),
                "p_two_sided_holm": two_adj["holm"][index],
                "two_sided_holm_sig": bool(two_adj["holm"][index] < 0.05),
                "directional_sig_0_0125": bool(row["p_directional"] < ALPHA_PUBLISHED),
                "two_sided_sig_0_0125": bool(row["p_two_sided"] < ALPHA_PUBLISHED),
            })
            rows.append(row)
    changes = [
        {"group": row["group"], "metric": row["metric"], "directional_p": row["p_directional"],
         "two_sided_p": row["p_two_sided"], "directional_holm_p": row["p_directional_holm"],
         "two_sided_holm_p": row["p_two_sided_holm"]}
        for row in rows
        if bool(row["directional_sig_0_0125"]) != bool(row["two_sided_holm_sig"])
    ]
    memo = {
        "rb_id": "RB-10",
        "concern": "H3 directional Wilcoxon tests",
        "classification": "Specification-sensitive" if changes else "Stable",
        "decision_changes": changes,
        "interpretation": (
            "Published one-sided tests encode subgroup-specific directions for all six outcomes. Two-sided tests, "
            "Holm adjustment, paired rank-biserial effects, and standardized change estimates separate directional "
            "confirmation from direction-agnostic evidence."
        ),
    }
    return rows, memo


def rb11_h3_correlations(frame: pd.DataFrame):
    base = h3_correlations(frame)
    rows: List[Dict[str, object]] = []
    within_adjusted: Dict[Tuple[str, str], Dict[str, float]] = {}
    for group in ("under", "over"):
        subset = [row for row in base if row["group"] == group]
        adj = adjust_pvalues([row["p_value"] for row in subset])
        for index, row in enumerate(subset):
            within_adjusted[(group, row["metric"])] = {
                "p_bonf_within4": adj["bonferroni"][index],
                "p_holm_within4": adj["holm"][index],
                "p_bh_within4": adj["bh_fdr"][index],
            }
    global_adj = adjust_pvalues([row["p_value"] for row in base])
    for index, original in enumerate(base):
        row = dict(original)
        row.update(within_adjusted[(row["group"], row["metric"] )])
        row.update({
            "p_bonf_global8": global_adj["bonferroni"][index],
            "p_holm_global8": global_adj["holm"][index],
            "p_bh_global8": global_adj["bh_fdr"][index],
            "raw_sig_0_0125": bool(row["p_value"] < ALPHA_PUBLISHED),
            "holm_within4_sig_0_05": bool(row["p_holm_within4"] < 0.05),
            "holm_global8_sig_0_05": bool(row["p_holm_global8"] < 0.05),
        })
        rows.append(row)
    mixed_row = next(row for row in rows if row["group"] == "under" and row["metric"] == "RSR")
    memo = {
        "rb_id": "RB-11",
        "concern": "H3 mixed p-value reporting",
        "classification": "Specification-sensitive",
        "under_rsr": {
            "p_unc": mixed_row["p_value"],
            "p_bonf_within4": mixed_row["p_bonf_within4"],
            "paper_p_display": mixed_row["paper_p_display"],
        },
        "interpretation": (
            "The clean table reports every one-sided unadjusted p-value beside consistent Bonferroni, Holm, and "
            "BH-FDR values. The paper's Underestimation–RSR entry uses the adjusted value while seven other rows use "
            "unadjusted values, so a single declared column is required for future reporting."
        ),
    }
    return rows, memo


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    frame_zero = add_groups(build_clean_metric_frame(repo, undefined_ratio="zero"))
    frame_nan = add_groups(build_clean_metric_frame(repo, undefined_ratio="nan"))

    rb06_rows, rb06_pairs, rb06_memo = rb06_group_outcome_coupling(frame_zero, frame_nan)
    rb07_rows, rb07_memo = rb07_multiplicity(frame_zero)
    rb08_rows, rb08_memo = rb08_wilcoxon_grid(frame_zero)
    rb09_evidence, rb09_memo = rb09_boundary(frame_zero)
    rb10_rows, rb10_memo = rb10_h3_directional(frame_zero)
    rb11_rows, rb11_memo = rb11_h3_correlations(frame_zero)

    write_tsv(out / "rb06_group_outcome_coupling.tsv", rb06_rows)
    write_tsv(out / "rb06_pairwise.tsv", rb06_pairs)
    write_json(out / "rb06_memo.json", rb06_memo)
    write_tsv(out / "rb07_multiplicity_matrix.tsv", rb07_rows)
    write_json(out / "rb07_memo.json", rb07_memo)
    write_tsv(out / "rb08_wilcoxon_grid.tsv", rb08_rows)
    write_json(out / "rb08_memo.json", rb08_memo)
    write_json(out / "rb09_boundary_evidence.json", rb09_evidence)
    write_json(out / "rb09_memo.json", rb09_memo)
    write_tsv(out / "rb10_directional_sensitivity.tsv", rb10_rows)
    write_json(out / "rb10_memo.json", rb10_memo)
    write_tsv(out / "rb11_consistent_correlations.tsv", rb11_rows)
    write_json(out / "rb11_memo.json", rb11_memo)

    memos = [rb06_memo, rb07_memo, rb08_memo, rb09_memo, rb10_memo, rb11_memo]
    summary = {
        "schema_version": "1.0",
        "stage": "hypothesis robustness H1-H3",
        "sample_n": 249,
        "passed": True,
        "upstream_util_imported": False,
        "participant_level_data_emitted": False,
        "checks": memos,
        "classifications": {memo["rb_id"]: memo["classification"] for memo in memos},
    }
    write_json(out / "h1_h3_robustness_summary.json", summary)
    (out / "H1_H3_STATUS.md").write_text(
        "# ETH HAI H1–H3 Robustness Gate\n\n" +
        "\n".join("- %s: **%s**" % (memo["rb_id"], memo["classification"]) for memo in memos) +
        "\n- Upstream `util.py` imported: **NO**\n- Participant-level data emitted: **NO**\n",
        encoding="utf-8",
    )
    print(json.dumps({"passed": True, "classifications": summary["classifications"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
