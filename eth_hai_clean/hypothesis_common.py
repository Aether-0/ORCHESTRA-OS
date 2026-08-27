"""Shared aggregate-only helpers for the ETH HAI hypothesis robustness audit."""
from __future__ import annotations

import csv
import json
import math
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests

ALPHA_PUBLISHED = 0.0125
CALIBRATION_ORDER = ("Underestimation", "Accurate", "Overestimation")
CONDITION_ORDER = (
    "no tutorial, no xai",
    "with tutorial, no xai",
    "no tutorial, with xai",
    "with tutorial, with xai",
)
METRICS = (
    ("Accuracy", "accuracy"),
    ("Agreement Fraction", "agreement_fraction"),
    ("Switch Fraction", "switch_fraction"),
    ("Accuracy-wid", "appropriate_reliance"),
    ("RAIR", "rair"),
    ("RSR", "rsr"),
)


def json_default(value):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, Path):
        return str(value)
    raise TypeError(type(value).__name__)


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=json_default) + "\n", encoding="utf-8")


def write_tsv(path: Path, rows: Sequence[Mapping[str, object]], fieldnames: Optional[Sequence[str]] = None) -> None:
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), delimiter="\t", lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: "" if row.get(key) is None else row.get(key) for key in fieldnames})


def calibration_label(value: float) -> str:
    if value < 0:
        return "Underestimation"
    if value > 0:
        return "Overestimation"
    return "Accurate"


def epsilon_squared_kruskal(h: float, n: int, k: int) -> float:
    if n <= k:
        return float("nan")
    return float(max(0.0, (float(h) - float(k) + 1.0) / (float(n) - float(k))))


def rank_biserial_paired(before: Sequence[float], after: Sequence[float]) -> float:
    diff = np.asarray(after, dtype=float) - np.asarray(before, dtype=float)
    nonzero = diff[diff != 0]
    if len(nonzero) == 0:
        return 0.0
    ranks = stats.rankdata(np.abs(nonzero), method="average")
    positive = float(ranks[nonzero > 0].sum())
    negative = float(ranks[nonzero < 0].sum())
    return (positive - negative) / float(positive + negative)


def cliffs_delta(x: Sequence[float], y: Sequence[float]) -> float:
    a = np.asarray(x, dtype=float)
    b = np.asarray(y, dtype=float)
    if len(a) == 0 or len(b) == 0:
        return float("nan")
    greater = 0
    less = 0
    for value in a:
        greater += int(np.sum(value > b))
        less += int(np.sum(value < b))
    return float(greater - less) / float(len(a) * len(b))


def bootstrap_ci(values: Sequence[float], statistic: str = "mean", draws: int = 20000, seed: int = 20260827) -> Dict[str, float]:
    x = np.asarray(values, dtype=float)
    if len(x) == 0:
        return {"estimate": float("nan"), "ci_low": float("nan"), "ci_high": float("nan"), "draws": 0}
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(x), size=(draws, len(x)))
    samples = x[indices]
    if statistic == "mean":
        distribution = samples.mean(axis=1)
        estimate = float(x.mean())
    elif statistic == "median":
        distribution = np.median(samples, axis=1)
        estimate = float(np.median(x))
    else:
        raise ValueError(statistic)
    low, high = np.quantile(distribution, [0.025, 0.975])
    return {"estimate": estimate, "ci_low": float(low), "ci_high": float(high), "draws": int(draws)}


def exact_sign_flip_sum_test(differences: Sequence[float]) -> Dict[str, object]:
    values = [int(round(abs(float(x)))) for x in differences if float(x) != 0.0]
    observed = int(round(sum(float(x) for x in differences)))
    if not values:
        return {"nonzero_n": 0, "observed_sum": observed, "p_greater": 1.0, "p_two_sided": 1.0, "total_assignments": 1}
    counts = Counter({0: 1})
    for magnitude in values:
        new_counts = Counter()
        for current, count in counts.items():
            new_counts[current + magnitude] += count
            new_counts[current - magnitude] += count
        counts = new_counts
    total = float(sum(counts.values()))
    p_greater = sum(count for value, count in counts.items() if value >= observed) / total
    p_two = sum(count for value, count in counts.items() if abs(value) >= abs(observed)) / total
    return {
        "nonzero_n": len(values),
        "observed_sum": observed,
        "p_greater": float(p_greater),
        "p_two_sided": float(min(1.0, p_two)),
        "total_assignments": int(total),
    }


def adjust_pvalues(pvalues: Sequence[float]) -> Dict[str, List[float]]:
    p = np.asarray(pvalues, dtype=float)
    return {
        "bonferroni": list(map(float, multipletests(p, method="bonferroni")[1])),
        "holm": list(map(float, multipletests(p, method="holm")[1])),
        "bh_fdr": list(map(float, multipletests(p, method="fdr_bh")[1])),
    }


def multiplicity_rows(family: str, tests: Sequence[Mapping[str, object]], alpha: float = ALPHA_PUBLISHED) -> List[Dict[str, object]]:
    pvalues = [float(row["p_value"]) for row in tests]
    adjusted = adjust_pvalues(pvalues)
    bonf_alpha = 0.05 / float(len(tests)) if tests else float("nan")
    output: List[Dict[str, object]] = []
    for index, row in enumerate(tests):
        out = dict(row)
        out.update({
            "family": family,
            "family_size": len(tests),
            "published_alpha": alpha,
            "bonferroni_alpha": bonf_alpha,
            "raw_sig_0_05": bool(pvalues[index] < 0.05),
            "published_sig_0_0125": bool(pvalues[index] < alpha),
            "bonferroni_sig": bool(pvalues[index] < bonf_alpha),
            "p_bonferroni": adjusted["bonferroni"][index],
            "bonferroni_adjusted_sig_0_05": bool(adjusted["bonferroni"][index] < 0.05),
            "p_holm": adjusted["holm"][index],
            "holm_sig_0_05": bool(adjusted["holm"][index] < 0.05),
            "p_bh_fdr": adjusted["bh_fdr"][index],
            "bh_fdr_sig_0_05": bool(adjusted["bh_fdr"][index] < 0.05),
        })
        output.append(out)
    return output


def kruskal_three(frame: pd.DataFrame, group_column: str, value_column: str) -> Dict[str, object]:
    groups = []
    counts: Dict[str, int] = {}
    means: Dict[str, Optional[float]] = {}
    medians: Dict[str, Optional[float]] = {}
    for label in CALIBRATION_ORDER:
        values = pd.to_numeric(frame.loc[frame[group_column] == label, value_column], errors="coerce").dropna().astype(float)
        groups.append(values.to_numpy())
        counts[label] = int(len(values))
        means[label] = float(values.mean()) if len(values) else None
        medians[label] = float(values.median()) if len(values) else None
    result = stats.kruskal(*groups)
    n = sum(counts.values())
    return {
        "H": float(result.statistic),
        "p_value": float(result.pvalue),
        "epsilon_squared": epsilon_squared_kruskal(float(result.statistic), n, 3),
        "group_counts": counts,
        "group_means": means,
        "group_medians": medians,
    }


def pairwise_mannwhitney(frame: pd.DataFrame, group_column: str, value_column: str) -> List[Dict[str, object]]:
    pairs = (("Underestimation", "Accurate"), ("Underestimation", "Overestimation"), ("Accurate", "Overestimation"))
    raw: List[Dict[str, object]] = []
    for left, right in pairs:
        x = pd.to_numeric(frame.loc[frame[group_column] == left, value_column], errors="coerce").dropna().astype(float)
        y = pd.to_numeric(frame.loc[frame[group_column] == right, value_column], errors="coerce").dropna().astype(float)
        result = stats.mannwhitneyu(x, y, alternative="two-sided")
        raw.append({
            "left": left,
            "right": right,
            "n_left": int(len(x)),
            "n_right": int(len(y)),
            "U": float(result.statistic),
            "p_value": float(result.pvalue),
            "cliffs_delta_left_minus_right": cliffs_delta(x, y),
        })
    adjusted = adjust_pvalues([row["p_value"] for row in raw])
    for index, row in enumerate(raw):
        row["p_holm"] = adjusted["holm"][index]
        row["holm_sig_0_05"] = bool(adjusted["holm"][index] < 0.05)
    return raw


def type2_anova_rows(model, outcome: str, specification: str) -> List[Dict[str, object]]:
    import statsmodels.api as sm
    table = sm.stats.anova_lm(model, typ=2)
    rows: List[Dict[str, object]] = []
    for term, values in table.iterrows():
        if term == "Residual":
            continue
        rows.append({
            "outcome": outcome,
            "specification": specification,
            "effect": str(term),
            "df": float(values["df"]),
            "F": float(values["F"]),
            "p_value": float(values["PR(>F)"]),
            "sum_sq": float(values["sum_sq"]),
        })
    return rows


def model_partial_eta_squared(anova_rows: Sequence[Mapping[str, object]], residual_sum_sq: float) -> List[Dict[str, object]]:
    output: List[Dict[str, object]] = []
    for row in anova_rows:
        out = dict(row)
        ss = float(out["sum_sq"])
        out["partial_eta_squared"] = ss / (ss + float(residual_sum_sq))
        output.append(out)
    return output
