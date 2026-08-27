"""Independent, transparent core for the CHI 2023 HAI reimplementation.

This module intentionally does not import or call the upstream util.py. The released
source is used only as provenance for the frozen task-order and condition mappings.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

SUBSTANTIVE_TASK_IDS: Tuple[int, ...] = (0, 1, 2, 3, 4, 5, 7, 8, 9, 10, 12, 13, 14, 15, 16, 17)
ATTENTION_TASK_IDS: Tuple[int, ...] = (6, 11, 18)

# Frozen, audited sequences after attention-task removal. Each sequence contains
# first experimental batch (first 6), four intervening tasks, and second batch (last 6).
TASK_ORDERS: Dict[int, Tuple[int, ...]] = {
    0: (1, 4, 5, 2, 3, 0, 7, 10, 8, 9, 14, 17, 13, 12, 16, 15),
    1: (12, 17, 13, 14, 16, 15, 9, 10, 8, 7, 5, 0, 2, 1, 4, 3),
    2: (1, 4, 5, 0, 3, 2, 8, 10, 9, 7, 15, 13, 17, 14, 16, 12),
    3: (12, 16, 17, 14, 13, 15, 10, 8, 9, 7, 2, 4, 5, 0, 3, 1),
    4: (3, 1, 4, 2, 0, 5, 8, 10, 9, 7, 17, 13, 15, 12, 16, 14),
    5: (16, 13, 14, 17, 12, 15, 9, 10, 8, 7, 0, 5, 1, 3, 4, 2),
    6: (4, 1, 3, 0, 2, 5, 8, 7, 10, 9, 17, 16, 13, 15, 14, 12),
    7: (12, 14, 16, 17, 15, 13, 8, 7, 10, 9, 3, 2, 4, 1, 5, 0),
    8: (2, 0, 4, 5, 3, 1, 8, 9, 7, 10, 16, 15, 17, 12, 13, 14),
    9: (12, 14, 16, 15, 13, 17, 10, 9, 8, 7, 0, 4, 5, 3, 2, 1),
}

CONDITION_LABELS: Dict[Tuple[int, int], str] = {
    (1, 0): "no tutorial, no xai",
    (0, 0): "with tutorial, no xai",
    (1, 1): "no tutorial, with xai",
    (0, 1): "with tutorial, with xai",
}


@dataclass(frozen=True)
class RelianceMetrics:
    correct_count: int
    task_count: int
    accuracy: float
    agreement_fraction: float
    initial_disagreement: int
    switch_fraction: float
    appropriate_reliance: float
    positive_ai_reliance: int
    negative_self_reliance: int
    positive_self_reliance: int
    negative_ai_reliance: int
    rair: Optional[float]
    rsr: Optional[float]

    def as_dict(self) -> Dict[str, object]:
        return asdict(self)


def validate_task_orders() -> None:
    expected = set(SUBSTANTIVE_TASK_IDS)
    if set(TASK_ORDERS) != set(range(10)):
        raise ValueError("Task-order keys must be exactly 0..9")
    for order_id, sequence in TASK_ORDERS.items():
        if len(sequence) != 16 or len(set(sequence)) != 16:
            raise ValueError("Order %d does not contain 16 unique tasks" % order_id)
        if set(sequence) != expected:
            raise ValueError("Order %d does not span the substantive task set" % order_id)


def condition_label(tutorial: int, xai: int) -> str:
    key = (int(tutorial), int(xai))
    if key not in CONDITION_LABELS:
        raise ValueError("Unknown condition coding: %r" % (key,))
    return CONDITION_LABELS[key]


def questionnaire_score(
    values: Sequence[float],
    reverse_positions_1_based: Iterable[int],
    max_scale: float,
    add_one: bool = True,
) -> float:
    reverse = set(int(x) for x in reverse_positions_1_based)
    scored: List[float] = []
    for index, raw in enumerate(values, start=1):
        value = float(raw) + (1.0 if add_one else 0.0)
        if index in reverse:
            value = max_scale + 1.0 - value
        scored.append(value)
    return float(np.mean(scored))


def score_ati(row: Mapping[str, object]) -> float:
    return questionnaire_score(
        [row["ati%d" % i] for i in range(1, 10)],
        reverse_positions_1_based=(3, 6, 8),
        max_scale=6,
        add_one=True,
    )


def score_propensity(row: Mapping[str, object]) -> float:
    return questionnaire_score(
        [row["pt%d" % i] for i in range(1, 4)],
        reverse_positions_1_based=(1,),
        max_scale=5,
        add_one=True,
    )


def score_trust(row: Mapping[str, object], batch: int) -> float:
    if batch == 1:
        fields = ("tia1_1", "tia1_2")
    elif batch == 2:
        fields = ("tia2_1", "tia2_2")
    else:
        raise ValueError("batch must be 1 or 2")
    return questionnaire_score([row[f] for f in fields], (), max_scale=5, add_one=True)


def calculate_reliance_metrics(
    row: Mapping[str, object],
    task_ids: Sequence[int],
    task_answers: Mapping[int, Tuple[str, str]],
    undefined_ratio: str = "zero",
) -> RelianceMetrics:
    if undefined_ratio not in ("zero", "nan"):
        raise ValueError("undefined_ratio must be 'zero' or 'nan'")

    correct_count = 0
    agreement_count = 0
    initial_disagreement = 0
    switch_count = 0
    correct_under_disagreement = 0
    positive_ai = 0
    negative_self = 0
    positive_self = 0
    negative_ai = 0

    for task_id in task_ids:
        correct_answer, ai_advice = task_answers[int(task_id)]
        initial = str(row["question%d" % task_id])
        final = str(row["advice%d" % task_id])

        if final == ai_advice:
            agreement_count += 1
        if initial != ai_advice:
            initial_disagreement += 1
            if final == ai_advice:
                switch_count += 1
            if final == correct_answer:
                correct_under_disagreement += 1

            if ai_advice == correct_answer:
                if final == ai_advice:
                    positive_ai += 1
                else:
                    negative_self += 1
            elif initial == correct_answer:
                if final == correct_answer:
                    positive_self += 1
                else:
                    negative_ai += 1

        if final == correct_answer:
            correct_count += 1

    n = len(task_ids)
    if n <= 0:
        raise ValueError("task_ids must not be empty")

    def ratio(numerator: int, denominator: int) -> Optional[float]:
        if denominator:
            return float(numerator) / float(denominator)
        return 0.0 if undefined_ratio == "zero" else None

    return RelianceMetrics(
        correct_count=correct_count,
        task_count=n,
        accuracy=float(correct_count) / float(n),
        agreement_fraction=float(agreement_count) / float(n),
        initial_disagreement=initial_disagreement,
        switch_fraction=float(switch_count) / float(initial_disagreement) if initial_disagreement else 0.0,
        appropriate_reliance=(
            float(correct_under_disagreement) / float(initial_disagreement)
            if initial_disagreement else 0.0
        ),
        positive_ai_reliance=positive_ai,
        negative_self_reliance=negative_self,
        positive_self_reliance=positive_self,
        negative_ai_reliance=negative_ai,
        rair=ratio(positive_ai, positive_ai + negative_self),
        rsr=ratio(positive_self, positive_self + negative_ai),
    )


def load_task_answers(repo: Path) -> Dict[int, Tuple[str, str]]:
    task_path = repo / "anonymous_data" / "selected_samples.csv"
    df = pd.read_csv(task_path, usecols=["answer", "AI-advice"])
    return {
        int(task_id): (str(row["answer"]), str(row["AI-advice"]))
        for task_id, row in df.iterrows()
    }


def load_valid_participants(repo: Path) -> pd.DataFrame:
    path = repo / "anonymous_data" / "all_valid_data.csv"
    df = pd.read_csv(path)
    complete = df.dropna(axis=0).copy()
    attention_score = (
        (pd.to_numeric(complete["attention_ati"]) == 3).astype(int)
        + (complete["attention6"].astype(str) == "B").astype(int)
        + (complete["attention11"].astype(str) == "D").astype(int)
        + (complete["attention18"].astype(str) == "C").astype(int)
    )
    valid = complete.loc[attention_score >= 4].copy()
    valid["condition"] = [
        condition_label(t, x)
        for t, x in zip(valid["tutorial"].astype(int), valid["XAI"].astype(int))
    ]
    return valid


def build_clean_metric_frame(repo: Path, undefined_ratio: str = "zero") -> pd.DataFrame:
    validate_task_orders()
    participants = load_valid_participants(repo)
    task_answers = load_task_answers(repo)

    records: List[Dict[str, object]] = []
    for _, row in participants.iterrows():
        order_id = int(row["question_order"])
        sequence = TASK_ORDERS[order_id]
        first_ids = sequence[:6]
        second_ids = sequence[-6:]
        overall_ids = first_ids + second_ids

        first = calculate_reliance_metrics(row, first_ids, task_answers, undefined_ratio)
        second = calculate_reliance_metrics(row, second_ids, task_answers, undefined_ratio)
        overall = calculate_reliance_metrics(row, overall_ids, task_answers, undefined_ratio)

        record: Dict[str, object] = {
            "condition": str(row["condition"]),
            "tutorial_raw": int(row["tutorial"]),
            "xai_raw": int(row["XAI"]),
            "order_id": order_id,
            "ati": score_ati(row),
            "propensity": score_propensity(row),
            "trust_first": score_trust(row, 1),
            "trust_second": score_trust(row, 2),
            "self_first": int(row["surveySelf1"]),
            "self_second": int(row["surveySelf2"]),
            "miscalibration_first": int(row["surveySelf1"]) - first.correct_count,
            "miscalibration_second": int(row["surveySelf2"]) - second.correct_count,
        }
        for prefix, metrics in (("first", first), ("second", second), ("overall", overall)):
            for key, value in metrics.as_dict().items():
                record["%s_%s" % (prefix, key)] = np.nan if value is None else value
        records.append(record)

    return pd.DataFrame.from_records(records)


def summarize_clean_frame(frame: pd.DataFrame) -> Dict[str, object]:
    condition_order = [
        "no tutorial, no xai",
        "with tutorial, no xai",
        "no tutorial, with xai",
        "with tutorial, with xai",
    ]
    condition_counts = {k: int((frame["condition"] == k).sum()) for k in condition_order}

    def calibration_counts(column: str) -> Dict[str, Dict[str, int]]:
        result: Dict[str, Dict[str, int]] = {}
        for condition in condition_order:
            values = frame.loc[frame["condition"] == condition, column]
            result[condition] = {
                "Under": int((values < 0).sum()),
                "Accurate": int((values == 0).sum()),
                "Over": int((values > 0).sum()),
            }
        return result

    descriptive_fields = {
        "ATI": "ati",
        "TiA-Propensity": "propensity",
        "Accuracy": "overall_accuracy",
        "Agreement_fraction": "overall_agreement_fraction",
        "switching_fraction": "overall_switch_fraction",
        "RAIR": "overall_rair",
        "RSR": "overall_rsr",
        "TiA-Trust-first": "trust_first",
        "TiA-Trust-second": "trust_second",
    }
    descriptives = {
        label: {
            "mean": float(frame[column].mean()),
            "sd_sample": float(frame[column].std(ddof=1)),
            "n": int(frame[column].notna().sum()),
        }
        for label, column in descriptive_fields.items()
    }

    first_mis = frame["miscalibration_first"]
    overall_groups = {
        "Under": int((first_mis < 0).sum()),
        "Accurate": int((first_mis == 0).sum()),
        "Over": int((first_mis > 0).sum()),
    }

    zero_denominators = {
        "first_rair": int(((frame["first_positive_ai_reliance"] + frame["first_negative_self_reliance"]) == 0).sum()),
        "first_rsr": int(((frame["first_positive_self_reliance"] + frame["first_negative_ai_reliance"]) == 0).sum()),
        "second_rair": int(((frame["second_positive_ai_reliance"] + frame["second_negative_self_reliance"]) == 0).sum()),
        "second_rsr": int(((frame["second_positive_self_reliance"] + frame["second_negative_ai_reliance"]) == 0).sum()),
        "overall_rair": int(((frame["overall_positive_ai_reliance"] + frame["overall_negative_self_reliance"]) == 0).sum()),
        "overall_rsr": int(((frame["overall_positive_self_reliance"] + frame["overall_negative_ai_reliance"]) == 0).sum()),
    }

    return {
        "sample_n": int(len(frame)),
        "condition_counts": condition_counts,
        "first_batch_calibration_by_condition": calibration_counts("miscalibration_first"),
        "second_batch_calibration_by_condition": calibration_counts("miscalibration_second"),
        "first_batch_calibration_overall": overall_groups,
        "descriptives": descriptives,
        "zero_denominator_counts": zero_denominators,
        "participant_level_data_emitted": False,
    }
