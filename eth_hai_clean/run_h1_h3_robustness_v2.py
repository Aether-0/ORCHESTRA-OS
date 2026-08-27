#!/usr/bin/env python3
"""Corrected RB-06 through RB-11 runner.

This wrapper preserves the completed RB-06 through RB-10 implementation and replaces
only the RB-11 aggregate-reporting function. The correction assigns global adjusted
p-values before evaluating their significance flags, avoiding same-expression access
to keys that have not yet been inserted. No upstream source or participant data are
modified or emitted.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from eth_hai_clean import run_h1_h3_robustness as base


def fixed_rb11_h3_correlations(frame):
    source_rows = base.h3_correlations(frame)
    rows: List[Dict[str, object]] = []
    within_adjusted: Dict[Tuple[str, str], Dict[str, float]] = {}

    for group in ("under", "over"):
        subset = [row for row in source_rows if row["group"] == group]
        adjusted = base.adjust_pvalues([row["p_value"] for row in subset])
        for index, row in enumerate(subset):
            within_adjusted[(group, row["metric"])] = {
                "p_bonf_within4": adjusted["bonferroni"][index],
                "p_holm_within4": adjusted["holm"][index],
                "p_bh_within4": adjusted["bh_fdr"][index],
            }

    global_adjusted = base.adjust_pvalues([row["p_value"] for row in source_rows])
    for index, original in enumerate(source_rows):
        row = dict(original)
        row.update(within_adjusted[(row["group"], row["metric"])])
        row["p_bonf_global8"] = global_adjusted["bonferroni"][index]
        row["p_holm_global8"] = global_adjusted["holm"][index]
        row["p_bh_global8"] = global_adjusted["bh_fdr"][index]
        row["raw_sig_0_0125"] = bool(row["p_value"] < base.ALPHA_PUBLISHED)
        row["holm_within4_sig_0_05"] = bool(row["p_holm_within4"] < 0.05)
        row["holm_global8_sig_0_05"] = bool(row["p_holm_global8"] < 0.05)
        rows.append(row)

    mixed_row = next(
        row for row in rows
        if row["group"] == "under" and row["metric"] == "RSR"
    )
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
            "The clean table reports every one-sided unadjusted p-value beside consistent "
            "Bonferroni, Holm, and BH-FDR values. The paper's Underestimation–RSR entry "
            "uses the adjusted value while seven other rows use unadjusted values, so a "
            "single declared column is required for future reporting."
        ),
    }
    return rows, memo


base.rb11_h3_correlations = fixed_rb11_h3_correlations


if __name__ == "__main__":
    raise SystemExit(base.main())
