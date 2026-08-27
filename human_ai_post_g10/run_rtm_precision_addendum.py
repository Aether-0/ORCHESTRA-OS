#!/usr/bin/env python3
"""Registered post-G10 regression-to-the-mean and precision addendum.

This script is a new, separately versioned analysis requested by the G10
methodological reviewer. It does not modify or overwrite any frozen direct,
robustness, or policy register. It emits aggregate evidence only.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import norm

from eth_hai_extension.core import (
    OUTCOME_COLUMNS,
    POLICIES,
    PRIMARY_CATEGORICAL_FEATURES,
    PRIMARY_NUMERIC_FEATURES,
    build_extension_frame,
)
from eth_hai_extension.estimators import fit_cross_fitted_nuisance, policy_value_aipw

SEED = 20260827
N_BOOTSTRAP = 10000
Z975 = float(norm.ppf(0.975))
GROUP_ORDER = ("All miscalibrated", "Underestimation", "Overestimation")

FROZEN_PRIMARY: Tuple[Mapping[str, object], ...] = (
    {"policy_id":"P01","policy_name":"Underestimators only","estimate":-0.0085975,"ci_low":-0.2287751,"ci_high":0.2115801,"coverage":72.0/249.0},
    {"policy_id":"P03","policy_name":"Overestimators only","estimate":-0.1083364,"ci_low":-0.3361151,"ci_high":0.1194424,"coverage":101.0/249.0},
    {"policy_id":"P05","policy_name":"All miscalibrated","estimate":-0.0197404,"ci_low":-0.1665400,"ci_high":0.1270593,"coverage":173.0/249.0},
)
FROZEN_ANCHOR = 0.0972
FROZEN_N = 249

METRICS: Tuple[Mapping[str, object], ...] = (
    {"metric_id":"absolute_miscalibration_improvement","label":"Absolute calibration improvement","baseline":"miscalibration_first","followup":"miscalibration_second","kind":"absolute_gap","bounded":False},
    {"metric_id":"accuracy_change","label":"Accuracy change","baseline":"first_accuracy","followup":"second_accuracy","kind":"difference","bounded":True},
    {"metric_id":"accuracy_wid_change","label":"Accuracy-wid change","baseline":"first_appropriate_reliance","followup":"second_appropriate_reliance","kind":"difference","bounded":True},
    {"metric_id":"rair_change","label":"RAIR change, released-zero","baseline":"first_rair","followup":"second_rair","kind":"difference","bounded":True},
    {"metric_id":"rsr_change","label":"RSR change, released-zero","baseline":"first_rsr","followup":"second_rsr","kind":"difference","bounded":True},
)


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_tsv(path: Path, rows: Sequence[Mapping[str, object]], fieldnames: Optional[Sequence[str]] = None) -> None:
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: "" if row.get(key) is None else row.get(key) for key in fieldnames})


def group_mask(frame: pd.DataFrame, group: str) -> np.ndarray:
    gap = frame["miscalibration_first"].to_numpy(dtype=float)
    if group == "All miscalibrated":
        return gap != 0
    if group == "Underestimation":
        return gap < 0
    if group == "Overestimation":
        return gap > 0
    raise ValueError(group)


def metric_change(frame: pd.DataFrame, spec: Mapping[str, object], followup_values: Optional[np.ndarray] = None) -> np.ndarray:
    baseline = frame[str(spec["baseline"])].to_numpy(dtype=float)
    followup = frame[str(spec["followup"])].to_numpy(dtype=float) if followup_values is None else np.asarray(followup_values, dtype=float)
    if spec["kind"] == "absolute_gap":
        return np.abs(baseline) - np.abs(followup)
    return followup - baseline


def percentile_interval(values: np.ndarray, alpha: float = 0.05) -> Tuple[float, float]:
    return float(np.quantile(values, alpha/2.0)), float(np.quantile(values, 1.0-alpha/2.0))


def bootstrap_mean_ci(values: np.ndarray, draws: int, rng: np.random.Generator) -> Tuple[float, float]:
    values = np.asarray(values, dtype=float)
    samples = values[rng.integers(0, len(values), size=(draws, len(values)))].mean(axis=1)
    return percentile_interval(samples)


def base_design(frame: pd.DataFrame, spec: Mapping[str, object], adjusted: bool) -> np.ndarray:
    baseline = frame[str(spec["baseline"])].to_numpy(dtype=float)
    cols: List[np.ndarray] = [np.ones(len(frame), dtype=float), baseline]
    if adjusted:
        if spec["kind"] != "absolute_gap":
            cols.append(frame["miscalibration_first"].to_numpy(dtype=float))
        cols.append(frame["xai_raw"].to_numpy(dtype=float))
        order = frame["order_id"].to_numpy(dtype=int)
        for level in range(1, 10):
            cols.append((order == level).astype(float))
    return np.column_stack(cols)


def fit_ols(x: np.ndarray, y: np.ndarray) -> Tuple[np.ndarray, np.ndarray, float, float]:
    beta = np.linalg.lstsq(x, y, rcond=None)[0]
    fitted = x @ beta
    residual = y - fitted
    ss_res = float(np.sum(residual**2))
    ss_tot = float(np.sum((y-np.mean(y))**2))
    r2 = 1.0 - ss_res/ss_tot if ss_tot > 0 else float("nan")
    corr = float(np.corrcoef(x[:,1], y)[0,1])
    return beta, residual, corr, r2


def simulate_rtm(controls: pd.DataFrame, tutorial_group: pd.DataFrame, spec: Mapping[str, object], adjusted: bool, draws: int, seed: int) -> Dict[str, object]:
    rng = np.random.default_rng(seed)
    n_c, n_t = len(controls), len(tutorial_group)
    x_c_full = base_design(controls, spec, adjusted)
    y_c_full = controls[str(spec["followup"])].to_numpy(dtype=float)
    x_t_full = base_design(tutorial_group, spec, adjusted)
    beta_full, residual_full, corr, r2 = fit_ols(x_c_full, y_c_full)
    pred = x_t_full @ beta_full
    if bool(spec["bounded"]):
        pred = np.clip(pred, 0.0, 1.0)
    elif spec["kind"] == "absolute_gap":
        pred = np.clip(np.rint(pred), -6.0, 6.0)
    benchmark_point = float(np.mean(metric_change(tutorial_group, spec, pred)))
    observed_point = float(np.mean(metric_change(tutorial_group, spec)))
    benchmark_draws = np.empty(draws)
    observed_draws = np.empty(draws)
    excess_draws = np.empty(draws)
    for draw in range(draws):
        c_idx = rng.integers(0, n_c, size=n_c)
        t_idx = rng.integers(0, n_t, size=n_t)
        c = controls.iloc[c_idx].reset_index(drop=True)
        t = tutorial_group.iloc[t_idx].reset_index(drop=True)
        x_c = base_design(c, spec, adjusted)
        y_c = c[str(spec["followup"])].to_numpy(dtype=float)
        beta, residual, _, _ = fit_ols(x_c, y_c)
        simulated = base_design(t, spec, adjusted) @ beta
        simulated += residual[rng.integers(0, len(residual), size=n_t)]
        if bool(spec["bounded"]):
            simulated = np.clip(simulated, 0.0, 1.0)
        elif spec["kind"] == "absolute_gap":
            simulated = np.clip(np.rint(simulated), -6.0, 6.0)
        benchmark = float(np.mean(metric_change(t, spec, simulated)))
        observed = float(np.mean(metric_change(t, spec)))
        benchmark_draws[draw] = benchmark
        observed_draws[draw] = observed
        excess_draws[draw] = observed - benchmark
    benchmark_ci = percentile_interval(benchmark_draws)
    observed_ci = percentile_interval(observed_draws)
    excess_ci = percentile_interval(excess_draws)
    return {
        "control_n":int(n_c),"tutorial_group_n":int(n_t),
        "baseline_followup_correlation_control":corr,"control_model_r2":r2,
        "control_baseline_slope":float(beta_full[1]),
        "observed_tutorial_change":observed_point,
        "observed_tutorial_ci_low":observed_ci[0],"observed_tutorial_ci_high":observed_ci[1],
        "rtm_benchmark_change":benchmark_point,
        "rtm_benchmark_ci_low":benchmark_ci[0],"rtm_benchmark_ci_high":benchmark_ci[1],
        "observed_minus_rtm":observed_point-benchmark_point,
        "excess_ci_low":excess_ci[0],"excess_ci_high":excess_ci[1],
        "excess_interval_excludes_zero":bool(excess_ci[0] > 0.0 or excess_ci[1] < 0.0),
    }


def natural_changes(frame: pd.DataFrame, draws: int) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for treatment, label in ((0,"No tutorial"),(1,"Tutorial")):
        arm = frame.loc[frame["treatment"] == treatment].reset_index(drop=True)
        for group in GROUP_ORDER:
            g = arm.loc[group_mask(arm, group)].reset_index(drop=True)
            for metric_index, spec in enumerate(METRICS):
                values = metric_change(g, spec)
                rng = np.random.default_rng(SEED+treatment*1000+metric_index*100+GROUP_ORDER.index(group))
                ci = bootstrap_mean_ci(values, draws, rng)
                rows.append({"treatment":label,"group":group,"metric_id":spec["metric_id"],"metric_label":spec["label"],"n":int(len(g)),"mean_change":float(np.mean(values)),"ci_low":ci[0],"ci_high":ci[1]})
    return rows


def rtm_simulation_rows(frame: pd.DataFrame, draws: int) -> List[Dict[str, object]]:
    controls = frame.loc[frame["treatment"] == 0].reset_index(drop=True)
    tutorials = frame.loc[frame["treatment"] == 1].reset_index(drop=True)
    rows: List[Dict[str, object]] = []
    for adjusted in (False, True):
        model = "Simple covariance RTM" if not adjusted else "Adjusted no-tutorial RTM"
        for group_index, group in enumerate(GROUP_ORDER):
            tg = tutorials.loc[group_mask(tutorials, group)].reset_index(drop=True)
            for metric_index, spec in enumerate(METRICS):
                result = simulate_rtm(controls, tg, spec, adjusted, draws, SEED+(100000 if adjusted else 0)+group_index*1000+metric_index*100)
                rows.append({"model":model,"group":group,"metric_id":spec["metric_id"],"metric_label":spec["label"],**result})
    return rows


def mde_rows() -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    thresholds = (("Unadjusted two-sided alpha=.05",0.05),("Holm first-step alpha=.05/3",0.05/3.0),("Source-study fixed alpha=.0125",0.0125))
    z_power = float(norm.ppf(0.80))
    for item in FROZEN_PRIMARY:
        se = (float(item["ci_high"])-float(item["ci_low"]))/(2.0*Z975)
        for label, alpha in thresholds:
            factor = float(norm.ppf(1.0-alpha/2.0))+z_power
            mde = factor*se
            rows.append({
                "policy_id":item["policy_id"],"policy_name":item["policy_name"],"coverage":item["coverage"],
                "observed_contrast":item["estimate"],"ci_low":item["ci_low"],"ci_high":item["ci_high"],
                "implied_standard_error":se,"threshold":label,"alpha":alpha,"power":0.80,
                "mde_absolute_contrast":mde,"mde_over_anchor":mde/abs(FROZEN_ANCHOR),
                "approx_n_to_detect_anchor_scale":int(math.ceil(FROZEN_N*(mde/abs(FROZEN_ANCHOR))**2)),
            })
    return rows


def policy_ratio_count_rows(frame: pd.DataFrame) -> List[Dict[str, object]]:
    frame = frame.copy()
    frame["second_rair_numerator"] = frame["second_positive_ai_reliance"].astype(float)
    frame["second_rair_opportunities"] = (frame["second_positive_ai_reliance"]+frame["second_negative_self_reliance"]).astype(float)
    frame["second_rsr_numerator"] = frame["second_positive_self_reliance"].astype(float)
    frame["second_rsr_opportunities"] = (frame["second_positive_self_reliance"]+frame["second_negative_ai_reliance"]).astype(float)
    columns = {"RAIR":("second_rair_numerator","second_rair_opportunities"),"RSR":("second_rsr_numerator","second_rsr_opportunities")}
    nuisance: Dict[str, Dict[str, np.ndarray]] = {}
    for pair in columns.values():
        for column in pair:
            nuisance[column] = fit_cross_fitted_nuisance(frame,column,PRIMARY_NUMERIC_FEATURES,PRIMARY_CATEGORICAL_FEATURES,n_splits=5,repeats=20,seed=SEED)
    treatment = frame["treatment"].to_numpy(dtype=int)
    rows: List[Dict[str, object]] = []
    for ratio_name,(num_col,den_col) in columns.items():
        for policy in POLICIES:
            d = frame["policy_%s"%policy.policy_id].to_numpy(dtype=int)
            num_pred, den_pred = nuisance[num_col], nuisance[den_col]
            num = policy_value_aipw(frame[num_col].to_numpy(dtype=float),treatment,d,num_pred["propensity"],num_pred["m0"],num_pred["m1"])
            den = policy_value_aipw(frame[den_col].to_numpy(dtype=float),treatment,d,den_pred["propensity"],den_pred["m0"],den_pred["m1"])
            ratio = num.policy_value/den.policy_value
            influence = (num.influence_values-ratio*den.influence_values)/den.policy_value
            se = float(np.std(influence,ddof=1)/np.sqrt(len(influence)))
            rows.append({
                "ratio":ratio_name,"policy_id":policy.policy_id,"policy_name":policy.name,
                "coverage_n":int(d.sum()),"coverage_fraction":float(np.mean(d)),
                "numerator_per_participant":num.policy_value,"opportunities_per_participant":den.policy_value,
                "expected_total_numerator_n249":num.policy_value*len(frame),
                "expected_total_opportunities_n249":den.policy_value*len(frame),
                "opportunity_pooled_ratio":ratio,"ratio_se":se,
                "ratio_ci_low":ratio-Z975*se,"ratio_ci_high":ratio+Z975*se,
            })
    return rows


def identity_rows(frame: pd.DataFrame) -> List[Dict[str, object]]:
    nuisance = fit_cross_fitted_nuisance(frame,OUTCOME_COLUMNS["O01"],PRIMARY_NUMERIC_FEATURES,PRIMARY_CATEGORICAL_FEATURES,n_splits=5,repeats=20,seed=SEED)
    y = frame[OUTCOME_COLUMNS["O01"]].to_numpy(dtype=float)
    a = frame["treatment"].to_numpy(dtype=int)
    est = {}
    for policy in POLICIES:
        d = frame["policy_%s"%policy.policy_id].to_numpy(dtype=int)
        est[policy.policy_id] = policy_value_aipw(y,a,d,nuisance["propensity"],nuisance["m0"],nuisance["m1"])
    pairs = (("P01-P07","P06-P00","P01 and P06 are complements"),("P02-P07","P05-P00","P02 and P05 are complements"),("P03-P07","P04-P00","P03 and P04 are complements"),("P00-P07","P07-P00","P00 and P07 are complements"))
    rows=[]
    for left_label,right_label,note in pairs:
        la,lb=left_label.split("-"); ra,rb=right_label.split("-")
        left=est[la].policy_value-est[lb].policy_value
        neg_right=-(est[ra].policy_value-est[rb].policy_value)
        rows.append({"identity":"%s = -(%s)"%(left_label,right_label),"left_value":left,"negative_right_value":neg_right,"absolute_residual":abs(left-neg_right),"explanation":note})
    return rows


def make_figures(rtm_rows: Sequence[Mapping[str, object]], mde: Sequence[Mapping[str, object]], out: Path) -> None:
    selected=[r for r in rtm_rows if r["model"]=="Simple covariance RTM"]
    labels=[]; observed=[]; benchmark=[]; low=[]; high=[]
    for group in GROUP_ORDER:
        for metric_id in ("absolute_miscalibration_improvement","accuracy_change"):
            row=next(r for r in selected if r["group"]==group and r["metric_id"]==metric_id)
            labels.append("%s\n%s"%(group.replace("All miscalibrated","All miscal."),"Abs cal." if metric_id.startswith("absolute") else "Accuracy"))
            observed.append(float(row["observed_tutorial_change"])); benchmark.append(float(row["rtm_benchmark_change"]))
            low.append(float(row["observed_tutorial_change"])-float(row["observed_tutorial_ci_low"])); high.append(float(row["observed_tutorial_ci_high"])-float(row["observed_tutorial_change"]))
    x=np.arange(len(labels)); width=.35
    fig,ax=plt.subplots(figsize=(12,6)); ax.bar(x-width/2,observed,width,label="Observed tutorial change"); ax.bar(x+width/2,benchmark,width,label="RTM benchmark")
    ax.errorbar(x-width/2,observed,yerr=np.vstack([low,high]),fmt="none",capsize=3,linewidth=1); ax.axhline(0,linewidth=1); ax.set_xticks(x); ax.set_xticklabels(labels); ax.set_ylabel("Mean change"); ax.set_title("Observed changes and covariance-based RTM benchmarks"); ax.legend(); fig.tight_layout(); fig.savefig(out/"post_g10_rtm_benchmark.png",dpi=200); plt.close(fig)
    plot=[r for r in mde if r["threshold"] in ("Unadjusted two-sided alpha=.05","Holm first-step alpha=.05/3")]
    policies=[r["policy_id"] for r in plot if r["threshold"]=="Unadjusted two-sided alpha=.05"]
    unadj=[next(float(r["mde_absolute_contrast"]) for r in plot if r["policy_id"]==p and r["threshold"]=="Unadjusted two-sided alpha=.05") for p in policies]
    holm=[next(float(r["mde_absolute_contrast"]) for r in plot if r["policy_id"]==p and r["threshold"]=="Holm first-step alpha=.05/3") for p in policies]
    x=np.arange(len(policies)); fig,ax=plt.subplots(figsize=(8,5)); ax.bar(x-width/2,unadj,width,label="alpha=.05"); ax.bar(x+width/2,holm,width,label="Holm first step"); ax.axhline(FROZEN_ANCHOR,linestyle="--",linewidth=1.5,label="Universal vs none anchor=.0972"); ax.set_xticks(x); ax.set_xticklabels(policies); ax.set_ylabel("Approximate 80% MDE"); ax.set_title("Minimum detectable primary-policy contrasts"); ax.legend(); fig.tight_layout(); fig.savefig(out/"post_g10_mde.png",dpi=200); plt.close(fig)


def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--repo",type=Path,required=True); parser.add_argument("--out",type=Path,required=True); parser.add_argument("--draws",type=int,default=N_BOOTSTRAP); parser.add_argument("--no-figures",action="store_true"); args=parser.parse_args()
    out=args.out.resolve(); out.mkdir(parents=True,exist_ok=True)
    frame=build_extension_frame(args.repo.resolve())
    if len(frame)!=249: raise AssertionError("Unexpected analytic sample")
    natural=natural_changes(frame,args.draws); rtm=rtm_simulation_rows(frame,args.draws); mde=mde_rows(); ratios=policy_ratio_count_rows(frame); identities=identity_rows(frame)
    write_tsv(out/"post_g10_natural_changes.tsv",natural); write_tsv(out/"post_g10_rtm_simulation.tsv",rtm); write_tsv(out/"post_g10_mde_precision.tsv",mde); write_tsv(out/"post_g10_ratio_count_opportunities.tsv",ratios); write_tsv(out/"post_g10_policy_linear_identities.tsv",identities)
    (out/"post_g10_split_half_feasibility.md").write_text("# Split-half calibration feasibility\n\nThe released data contain one self-assessment after the entire six-task first batch. They do not contain task-level confidence or separate self-assessments for task halves. A split-half calibration group would therefore require inventing how the six-task self-assessment should be allocated across three-task subsets. That arbitrary construction would not be a clean held-out calibration analysis. The post-G10 addendum therefore uses an observed-covariance RTM benchmark and a no-tutorial natural-change benchmark, and reserves split-half calibration for a future study with repeated or task-level self-assessment.\n",encoding="utf-8")
    key=[row for row in rtm if row["model"]=="Simple covariance RTM" and row["metric_id"] in ("absolute_miscalibration_improvement","accuracy_change")]
    summary={"schema_version":"1.0","stage":"registered post-G10 RTM and precision addendum","sample_n":int(len(frame)),"bootstrap_draws":int(args.draws),"frozen_registers_modified":False,"participant_level_data_emitted":False,"causal_identification_claimed":False,"split_half_calibration_performed":False,"split_half_reason":"No half-specific self-assessment exists in the released data.","primary_anchor":FROZEN_ANCHOR,"rtm_key_results":key,"mde_rows_n":len(mde),"ratio_count_rows_n":len(ratios),"linear_identity_max_absolute_residual":max(float(r["absolute_residual"]) for r in identities)}
    write_json(out/"post_g10_summary.json",summary)
    (out/"POST_G10_STATUS.md").write_text("# Post-G10 RTM and Precision Addendum Status\n\n- Execution: **PASS**\n- Analytic sample: **249**\n- Bootstrap draws: **%d**\n- Frozen registers modified: **NO**\n- Participant-level data emitted: **NO**\n- Causal identification claimed: **NO**\n- Split-half calibration: **NOT PERFORMED — half-specific self-assessment unavailable**\n"%args.draws,encoding="utf-8")
    if not args.no_figures: make_figures(rtm,mde,out)
    print(json.dumps({"status":"PASS","sample_n":len(frame),"draws":args.draws,"frozen_registers_modified":False,"participant_level_data_emitted":False},sort_keys=True))
    return 0

if __name__=="__main__": raise SystemExit(main())
