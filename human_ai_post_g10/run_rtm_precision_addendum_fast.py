#!/usr/bin/env python3
"""Fast fixed-model residual-bootstrap wrapper for the post-G10 addendum."""
from __future__ import annotations

from typing import Dict, Mapping

import numpy as np
import pandas as pd

from human_ai_post_g10 import run_rtm_precision_addendum as base


def simulate_rtm(
    controls: pd.DataFrame,
    tutorial_group: pd.DataFrame,
    spec: Mapping[str, object],
    adjusted: bool,
    draws: int,
    seed: int,
) -> Dict[str, object]:
    """Fit the no-tutorial model once, then resample tutorial rows and residuals.

    This is a model-based regression-to-the-mean benchmark, not a full model-
    refit bootstrap and not a causal adjustment.
    """
    rng = np.random.default_rng(seed)
    n_c = len(controls)
    n_t = len(tutorial_group)
    x_c = base.base_design(controls, spec, adjusted)
    y_c = controls[str(spec["followup"])].to_numpy(dtype=float)
    x_t = base.base_design(tutorial_group, spec, adjusted)
    beta, residual, corr, r2 = base.fit_ols(x_c, y_c)

    predicted_all = x_t @ beta
    baseline_all = tutorial_group[str(spec["baseline"])].to_numpy(dtype=float)
    observed_followup_all = tutorial_group[str(spec["followup"])].to_numpy(dtype=float)

    point_followup = predicted_all.copy()
    if bool(spec["bounded"]):
        point_followup = np.clip(point_followup, 0.0, 1.0)
    elif spec["kind"] == "absolute_gap":
        point_followup = np.clip(np.rint(point_followup), -6.0, 6.0)
    benchmark_point = float(np.mean(base.metric_change(tutorial_group, spec, point_followup)))
    observed_point = float(np.mean(base.metric_change(tutorial_group, spec)))

    t_idx = rng.integers(0, n_t, size=(draws, n_t))
    r_idx = rng.integers(0, len(residual), size=(draws, n_t))
    simulated = predicted_all[t_idx] + residual[r_idx]
    if bool(spec["bounded"]):
        simulated = np.clip(simulated, 0.0, 1.0)
    elif spec["kind"] == "absolute_gap":
        simulated = np.clip(np.rint(simulated), -6.0, 6.0)

    baseline_boot = baseline_all[t_idx]
    observed_followup_boot = observed_followup_all[t_idx]
    if spec["kind"] == "absolute_gap":
        benchmark_draws = (np.abs(baseline_boot) - np.abs(simulated)).mean(axis=1)
        observed_draws = (np.abs(baseline_boot) - np.abs(observed_followup_boot)).mean(axis=1)
    else:
        benchmark_draws = (simulated - baseline_boot).mean(axis=1)
        observed_draws = (observed_followup_boot - baseline_boot).mean(axis=1)
    excess_draws = observed_draws - benchmark_draws

    benchmark_ci = base.percentile_interval(benchmark_draws)
    observed_ci = base.percentile_interval(observed_draws)
    excess_ci = base.percentile_interval(excess_draws)
    return {
        "control_n": int(n_c),
        "tutorial_group_n": int(n_t),
        "baseline_followup_correlation_control": corr,
        "control_model_r2": r2,
        "control_baseline_slope": float(beta[1]),
        "observed_tutorial_change": observed_point,
        "observed_tutorial_ci_low": observed_ci[0],
        "observed_tutorial_ci_high": observed_ci[1],
        "rtm_benchmark_change": benchmark_point,
        "rtm_benchmark_ci_low": benchmark_ci[0],
        "rtm_benchmark_ci_high": benchmark_ci[1],
        "observed_minus_rtm": observed_point - benchmark_point,
        "excess_ci_low": excess_ci[0],
        "excess_ci_high": excess_ci[1],
        "excess_interval_excludes_zero": bool(excess_ci[0] > 0.0 or excess_ci[1] < 0.0),
        "bootstrap_type": "fixed-model residual and tutorial-participant bootstrap",
    }


base.simulate_rtm = simulate_rtm

if __name__ == "__main__":
    raise SystemExit(base.main())
