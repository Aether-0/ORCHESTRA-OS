"""Associational standardization estimators and deterministic fold utilities.

The functions in this module support the registered extension. They do not claim
causal identification when the condition-assignment mechanism is undocumented.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterator, Sequence, Tuple

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


@dataclass(frozen=True)
class PolicyValueEstimate:
    policy_value: float
    standard_error: float
    influence_values: np.ndarray


def clip_propensity(values: Sequence[float], lower: float = 0.025, upper: float = 0.975) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    if not (0.0 < lower < upper < 1.0):
        raise ValueError("Invalid propensity clipping interval")
    return np.clip(values, lower, upper)


def policy_value_or(policy: Sequence[int], m0: Sequence[float], m1: Sequence[float]) -> PolicyValueEstimate:
    d = np.asarray(policy, dtype=int)
    m0 = np.asarray(m0, dtype=float)
    m1 = np.asarray(m1, dtype=float)
    selected = np.where(d == 1, m1, m0)
    value = float(np.mean(selected))
    influence = selected - value
    se = float(np.std(influence, ddof=1) / np.sqrt(len(influence))) if len(influence) > 1 else 0.0
    return PolicyValueEstimate(value, se, influence)


def policy_value_ipw(
    y: Sequence[float],
    treatment: Sequence[int],
    policy: Sequence[int],
    propensity: Sequence[float],
    lower: float = 0.025,
    upper: float = 0.975,
) -> PolicyValueEstimate:
    y = np.asarray(y, dtype=float)
    a = np.asarray(treatment, dtype=int)
    d = np.asarray(policy, dtype=int)
    e = clip_propensity(propensity, lower, upper)
    p_d = np.where(d == 1, e, 1.0 - e)
    match = (a == d).astype(float)
    contributions = match * y / p_d
    value = float(np.mean(contributions))
    influence = contributions - value
    se = float(np.std(influence, ddof=1) / np.sqrt(len(influence))) if len(influence) > 1 else 0.0
    return PolicyValueEstimate(value, se, influence)


def policy_value_aipw(
    y: Sequence[float],
    treatment: Sequence[int],
    policy: Sequence[int],
    propensity: Sequence[float],
    m0: Sequence[float],
    m1: Sequence[float],
    lower: float = 0.025,
    upper: float = 0.975,
) -> PolicyValueEstimate:
    y = np.asarray(y, dtype=float)
    a = np.asarray(treatment, dtype=int)
    d = np.asarray(policy, dtype=int)
    e = clip_propensity(propensity, lower, upper)
    m0 = np.asarray(m0, dtype=float)
    m1 = np.asarray(m1, dtype=float)
    selected = np.where(d == 1, m1, m0)
    observed_model = np.where(a == 1, m1, m0)
    p_d = np.where(d == 1, e, 1.0 - e)
    match = (a == d).astype(float)
    pseudo = selected + match * (y - observed_model) / p_d
    value = float(np.mean(pseudo))
    influence = pseudo - value
    se = float(np.std(influence, ddof=1) / np.sqrt(len(influence))) if len(influence) > 1 else 0.0
    return PolicyValueEstimate(value, se, influence)


def policy_contrast(left: PolicyValueEstimate, right: PolicyValueEstimate) -> PolicyValueEstimate:
    if len(left.influence_values) != len(right.influence_values):
        raise ValueError("Influence arrays must have equal length")
    influence = left.influence_values - right.influence_values
    value = float(left.policy_value - right.policy_value)
    se = float(np.std(influence, ddof=1) / np.sqrt(len(influence))) if len(influence) > 1 else 0.0
    return PolicyValueEstimate(value, se, influence)


def composite_stratum(frame: pd.DataFrame) -> pd.Series:
    required = ["treatment", "xai_raw", "calibration_group"]
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise KeyError("Missing fold-stratification columns: %r" % missing)
    return (
        frame["treatment"].astype(str)
        + "|" + frame["xai_raw"].astype(str)
        + "|" + frame["calibration_group"].astype(str)
    )


def repeated_stratified_folds(
    frame: pd.DataFrame,
    n_splits: int = 5,
    repeats: int = 20,
    seed: int = 20260827,
) -> Iterator[Tuple[int, int, np.ndarray, np.ndarray]]:
    strata = composite_stratum(frame)
    counts = strata.value_counts()
    if int(counts.min()) < int(n_splits):
        raise ValueError("At least one fold stratum has fewer observations than n_splits")
    dummy = np.zeros(len(frame), dtype=int)
    for repeat in range(int(repeats)):
        splitter = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed + repeat)
        for fold, (train_index, test_index) in enumerate(splitter.split(dummy, strata)):
            yield repeat, fold, train_index.astype(int), test_index.astype(int)


def make_preprocessor(numeric_features: Sequence[str], categorical_features: Sequence[str]) -> ColumnTransformer:
    numeric = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
    ])
    categorical = Pipeline([
        ("impute", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore")),
    ])
    return ColumnTransformer([
        ("numeric", numeric, list(numeric_features)),
        ("categorical", categorical, list(categorical_features)),
    ])


def fit_cross_fitted_nuisance(
    frame: pd.DataFrame,
    outcome_column: str,
    numeric_features: Sequence[str],
    categorical_features: Sequence[str],
    n_splits: int = 5,
    repeats: int = 20,
    seed: int = 20260827,
) -> Dict[str, np.ndarray]:
    """Return repeat-averaged out-of-fold propensity and outcome predictions."""
    y = pd.to_numeric(frame[outcome_column], errors="raise").to_numpy(dtype=float)
    a = pd.to_numeric(frame["treatment"], errors="raise").to_numpy(dtype=int)
    features = frame[list(numeric_features) + list(categorical_features)].copy()
    n = len(frame)
    e_sum = np.zeros(n, dtype=float)
    m0_sum = np.zeros(n, dtype=float)
    m1_sum = np.zeros(n, dtype=float)
    seen = np.zeros(n, dtype=int)

    for repeat, fold, train_index, test_index in repeated_stratified_folds(frame, n_splits, repeats, seed):
        x_train = features.iloc[train_index]
        x_test = features.iloc[test_index]
        a_train = a[train_index]
        y_train = y[train_index]

        propensity = Pipeline([
            ("preprocess", make_preprocessor(numeric_features, categorical_features)),
            ("model", LogisticRegression(C=1.0, penalty="l2", solver="liblinear", max_iter=1000)),
        ])
        propensity.fit(x_train, a_train)
        e_pred = propensity.predict_proba(x_test)[:, 1]

        predictions = {}
        for arm in (0, 1):
            arm_mask = a_train == arm
            if int(np.sum(arm_mask)) < 2:
                raise ValueError("Insufficient training observations in treatment arm %d" % arm)
            outcome_model = Pipeline([
                ("preprocess", make_preprocessor(numeric_features, categorical_features)),
                ("model", Ridge(alpha=1.0)),
            ])
            outcome_model.fit(x_train.iloc[arm_mask], y_train[arm_mask])
            predictions[arm] = outcome_model.predict(x_test)

        e_sum[test_index] += e_pred
        m0_sum[test_index] += predictions[0]
        m1_sum[test_index] += predictions[1]
        seen[test_index] += 1

    if not np.all(seen == repeats):
        raise AssertionError("Each row must receive exactly one test prediction per repeat")
    return {
        "propensity": e_sum / seen,
        "m0": m0_sum / seen,
        "m1": m1_sum / seen,
        "prediction_count": seen,
    }


def fit_cross_fitted_propensity(
    frame: pd.DataFrame,
    numeric_features: Sequence[str],
    categorical_features: Sequence[str],
    n_splits: int = 5,
    repeats: int = 20,
    seed: int = 20260827,
) -> Dict[str, np.ndarray]:
    """Return repeat-averaged out-of-fold tutorial-assignment probabilities."""
    a = pd.to_numeric(frame["treatment"], errors="raise").to_numpy(dtype=int)
    features = frame[list(numeric_features) + list(categorical_features)].copy()
    n = len(frame)
    e_sum = np.zeros(n, dtype=float)
    seen = np.zeros(n, dtype=int)
    for repeat, fold, train_index, test_index in repeated_stratified_folds(frame, n_splits, repeats, seed):
        model = Pipeline([
            ("preprocess", make_preprocessor(numeric_features, categorical_features)),
            ("model", LogisticRegression(C=1.0, penalty="l2", solver="liblinear", max_iter=1000)),
        ])
        model.fit(features.iloc[train_index], a[train_index])
        e_sum[test_index] += model.predict_proba(features.iloc[test_index])[:, 1]
        seen[test_index] += 1
    if not np.all(seen == repeats):
        raise AssertionError("Each row must receive one propensity prediction per repeat")
    return {"propensity": e_sum / seen, "prediction_count": seen}
