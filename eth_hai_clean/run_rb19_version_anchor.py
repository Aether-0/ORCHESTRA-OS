#!/usr/bin/env python3
"""Generate deterministic aggregate anchors for RB-19 package-version sensitivity.

The script is intentionally compatible with both the frozen Python 3.8 stack and a
current stable Python stack. It uses the independent clean core, never imports the
upstream util.py, and emits no participant-level rows or identifiers.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
import platform
import sys
import warnings
from pathlib import Path
from typing import Dict, List, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy import stats
import scipy
import statsmodels
import statsmodels.api as sm
import statsmodels.formula.api as smf

from eth_hai_clean.core import build_clean_metric_frame
from eth_hai_clean.hypothesis_common import METRICS, calibration_label, write_json, write_tsv

TUTORIAL_RAW = 0


def add_anchor(rows: List[Dict[str, object]], key: str, section: str, quantity: str,
               value: object, alpha: object = None) -> None:
    rows.append({
        "key": key,
        "section": section,
        "quantity": quantity,
        "value": value,
        "alpha": alpha,
    })


def prepare(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy().reset_index(drop=True)
    out["group_first"] = out["miscalibration_first"].astype(float).map(calibration_label)
    out["tutorial_yes"] = 1 - out["tutorial_raw"].astype(int)
    out["xai_yes"] = out["xai_raw"].astype(int)
    out["avg_trust"] = (out["trust_first"] + out["trust_second"]) / 2.0
    for _, metric in METRICS:
        out["delta_%s" % metric] = out["second_%s" % metric] - out["first_%s" % metric]
    out["delta_miscalibration"] = out["miscalibration_second"] - out["miscalibration_first"]
    return out


def wilcoxon(before: Sequence[float], after: Sequence[float], alternative: str):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = stats.wilcoxon(before, after, alternative=alternative, zero_method="wilcox", correction=False, mode="auto")
    return float(result.statistic), float(result.pvalue)


def stable_quartiles(frame: pd.DataFrame):
    n_q = int(math.ceil(len(frame) * 0.25))
    ranked = frame.sort_values("first_accuracy", ascending=False, kind="mergesort")
    return ranked.iloc[:n_q], ranked.iloc[-n_q:]


def package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--stack-label", required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    frame = prepare(build_clean_metric_frame(repo, undefined_ratio="zero"))
    rows: List[Dict[str, object]] = []

    # Core sample and descriptive anchors.
    add_anchor(rows, "sample_n", "Core", "count", int(len(frame)))
    for condition, count in frame["condition"].value_counts().sort_index().items():
        add_anchor(rows, "condition_n::%s" % condition, "Core", "count", int(count))
    descriptives = {
        "ati_mean": frame["ati"].mean(),
        "ati_sd_sample": frame["ati"].std(ddof=1),
        "propensity_mean": frame["propensity"].mean(),
        "overall_accuracy_mean": frame["overall_accuracy"].mean(),
        "overall_agreement_mean": frame["overall_agreement_fraction"].mean(),
        "overall_switch_mean": frame["overall_switch_fraction"].mean(),
        "overall_rair_mean": frame["overall_rair"].mean(),
        "overall_rsr_mean": frame["overall_rsr"].mean(),
        "trust_first_mean": frame["trust_first"].mean(),
        "trust_second_mean": frame["trust_second"].mean(),
    }
    for key, value in descriptives.items():
        add_anchor(rows, key, "Descriptive", "estimate", float(value))

    # H1 Table 3 anchors.
    for label, metric in METRICS:
        groups = [
            frame.loc[frame["group_first"] == group, "first_%s" % metric].dropna().astype(float).to_numpy()
            for group in ("Underestimation", "Accurate", "Overestimation")
        ]
        result = stats.kruskal(*groups)
        add_anchor(rows, "H1::%s::H" % metric, "H1", "statistic", float(result.statistic))
        add_anchor(rows, "H1::%s::p" % metric, "H1", "p_value", float(result.pvalue), 0.0125)

    # H2 anchors.
    tutorial = frame.loc[(frame["tutorial_raw"] == TUTORIAL_RAW) & (frame["miscalibration_first"] != 0)].copy()
    for group, subset in (
        ("all", tutorial),
        ("under", tutorial.loc[tutorial["miscalibration_first"] < 0]),
        ("over", tutorial.loc[tutorial["miscalibration_first"] > 0]),
    ):
        before = subset["miscalibration_first"].abs().astype(float).to_numpy()
        after = subset["miscalibration_second"].abs().astype(float).to_numpy()
        statistic, p = wilcoxon(before, after, "greater")
        add_anchor(rows, "H2::%s::n" % group, "H2", "count", int(len(subset)))
        add_anchor(rows, "H2::%s::W" % group, "H2", "statistic", statistic)
        add_anchor(rows, "H2::%s::p" % group, "H2", "p_value", p, 0.0125)

    # H3 Table 4 and Table 5 anchors.
    tutorial_all = frame.loc[frame["tutorial_raw"] == TUTORIAL_RAW].copy()
    for group, subset, alternative in (
        ("under", tutorial_all.loc[tutorial_all["miscalibration_first"] < 0], "greater"),
        ("over", tutorial_all.loc[tutorial_all["miscalibration_first"] > 0], "less"),
    ):
        for label, metric in METRICS:
            before = subset["first_%s" % metric].astype(float).to_numpy()
            after = subset["second_%s" % metric].astype(float).to_numpy()
            statistic, p = wilcoxon(before, after, alternative)
            add_anchor(rows, "H3_T4::%s::%s::W" % (group, metric), "H3", "statistic", statistic)
            add_anchor(rows, "H3_T4::%s::%s::p" % (group, metric), "H3", "p_value", p, 0.0125)
        for label, metric in (("accuracy", "accuracy"), ("accuracy_wid", "appropriate_reliance"), ("rair", "rair"), ("rsr", "rsr")):
            pair = subset[["delta_miscalibration", "delta_%s" % metric]].dropna()
            corr = stats.spearmanr(pair["delta_miscalibration"], pair["delta_%s" % metric], alternative="less")
            add_anchor(rows, "H3_T5::%s::%s::rho" % (group, metric), "H3", "statistic", float(corr.statistic))
            add_anchor(rows, "H3_T5::%s::%s::p" % (group, metric), "H3", "p_value", float(corr.pvalue), 0.0125)

    # H4 Type II ANOVA anchors.
    term_map = {
        "Tutorial": "C(tutorial_yes)",
        "XAI": "C(xai_yes)",
        "Interaction": "C(tutorial_yes):C(xai_yes)",
    }
    for label, metric in METRICS:
        data = frame[["tutorial_yes", "xai_yes", "second_%s" % metric]].dropna().rename(columns={"second_%s" % metric: "outcome"})
        model = smf.ols("outcome ~ C(tutorial_yes) * C(xai_yes)", data=data).fit()
        table = sm.stats.anova_lm(model, typ=2)
        for effect, term in term_map.items():
            add_anchor(rows, "H4::%s::%s::F" % (metric, effect), "H4", "statistic", float(table.loc[term, "F"]))
            add_anchor(rows, "H4::%s::%s::p" % (metric, effect), "H4", "p_value", float(table.loc[term, "PR(>F)"]), 0.0125)

    # DKE released-stable Table 8 anchors.
    top, bottom = stable_quartiles(frame)
    for label, metric in METRICS[1:]:
        x = top["first_%s" % metric].astype(float).to_numpy()
        y = bottom["first_%s" % metric].astype(float).to_numpy()
        result = stats.kruskal(x, y)
        add_anchor(rows, "DKE::%s::H" % metric, "DKE", "statistic", float(result.statistic))
        add_anchor(rows, "DKE::%s::p" % metric, "DKE", "p_value", float(result.pvalue), 0.0125)

    # Trust anchors.
    tutorial_trust = frame.loc[frame["tutorial_raw"] == TUTORIAL_RAW]
    statistic, p = wilcoxon(tutorial_trust["trust_first"], tutorial_trust["trust_second"], "two-sided")
    add_anchor(rows, "Trust::tutorial::W", "Trust", "statistic", statistic)
    add_anchor(rows, "Trust::tutorial::p", "Trust", "p_value", p, 0.0125)

    trust_model = smf.ols("avg_trust ~ C(group_first) + ati + propensity", data=frame).fit()
    trust_table = sm.stats.anova_lm(trust_model, typ=2)
    for effect, term in (("calibration_group", "C(group_first)"), ("ATI", "ati"), ("propensity", "propensity")):
        add_anchor(rows, "Trust_ANCOVA::%s::F" % effect, "Trust", "statistic", float(trust_table.loc[term, "F"]))
        add_anchor(rows, "Trust_ANCOVA::%s::p" % effect, "Trust", "p_value", float(trust_table.loc[term, "PR(>F)"]), 0.0125)
    corr = stats.spearmanr(frame["propensity"], frame["avg_trust"])
    add_anchor(rows, "Trust::propensity_avg_trust::rho", "Trust", "statistic", float(corr.statistic))
    add_anchor(rows, "Trust::propensity_avg_trust::p", "Trust", "p_value", float(corr.pvalue), 0.0125)

    versions = {
        "stack_label": args.stack_label,
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scipy": scipy.__version__,
        "statsmodels": statsmodels.__version__,
        "patsy": package_version("patsy"),
    }
    payload = {
        "schema_version": "1.0",
        "stack": versions,
        "anchors_n": len(rows),
        "anchors": rows,
        "upstream_util_imported": False,
        "participant_level_data_emitted": False,
    }
    write_json(out / "version_anchor_results.json", payload)
    write_tsv(out / "version_anchor_results.tsv", rows)
    write_json(out / "version_stack.json", versions)
    (out / "VERSION_STATUS.md").write_text(
        "# RB-19 Version Anchor\n\n"
        "- Stack: **%s**\n"
        "- Python: **%s**\n"
        "- Anchors generated: **%d**\n"
        "- Upstream `util.py` imported: **NO**\n"
        "- Participant-level data emitted: **NO**\n" % (args.stack_label, versions["python"], len(rows)),
        encoding="utf-8",
    )
    print(json.dumps({"stack": args.stack_label, "python": versions["python"], "anchors_n": len(rows)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
