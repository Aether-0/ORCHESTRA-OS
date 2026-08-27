"""Aggregate regression-to-the-mean diagnostics for the post-G10 addendum."""
from __future__ import annotations
from typing import Dict, Sequence, Tuple
import numpy as np
import pandas as pd


def calibration_label(v: float) -> str:
    return "Underestimation" if float(v)<0 else "Overestimation" if float(v)>0 else "Accurate"


def design(frame: pd.DataFrame, baseline: str, include_tutorial: bool) -> np.ndarray:
    parts=[np.ones((len(frame),1)), pd.to_numeric(frame[baseline],errors="raise").to_numpy(float)[:,None]]
    if include_tutorial:
        parts.append((1-pd.to_numeric(frame["tutorial_raw"],errors="raise").to_numpy(int)).astype(float)[:,None])
    parts.append(pd.to_numeric(frame["xai_raw"],errors="raise").to_numpy(float)[:,None])
    d=pd.get_dummies(frame["order_id"].astype(int),prefix="order",drop_first=True)
    if d.shape[1]: parts.append(d.to_numpy(float))
    return np.column_stack(parts)


def fit(frame: pd.DataFrame, baseline: str, followup: str, include_tutorial: bool):
    x=design(frame,baseline,include_tutorial)
    y=pd.to_numeric(frame[followup],errors="raise").to_numpy(float)
    beta=np.linalg.lstsq(x,y,rcond=None)[0]
    b=pd.to_numeric(frame[baseline],errors="raise").to_numpy(float)
    corr=float(np.corrcoef(b,y)[0,1]) if np.std(b) and np.std(y) else float("nan")
    return x.dot(beta), float(beta[1]), corr


def stratified_indices(frame: pd.DataFrame, strata: Sequence[str], rng) -> np.ndarray:
    chunks=[]
    for values in frame.groupby(list(strata),sort=True,dropna=False).indices.values():
        values=np.asarray(values,int); chunks.append(rng.choice(values,size=len(values),replace=True))
    return np.concatenate(chunks)


def ci(values) -> Tuple[float,float]:
    a=np.asarray(values,float); return float(np.percentile(a,2.5)),float(np.percentile(a,97.5))


def benchmark(reference: pd.DataFrame, group: str, baseline: str, followup: str,
              analysis: str, outcome: str, include_tutorial: bool,
              bootstrap_strata: Sequence[str], permutation_strata: Sequence[str],
              bootstrap_draws: int, permutation_draws: int, seed: int) -> Dict[str,object]:
    ref=reference.reset_index(drop=True).copy()
    ref["calibration_group"]=ref["miscalibration_first"].map(calibration_label)
    mask=(ref["calibration_group"]!="Accurate") if group=="Miscalibrated" else (ref["calibration_group"]==group)
    pred,slope,corr=fit(ref,baseline,followup,include_tutorial)
    b=pd.to_numeric(ref[baseline],errors="raise").to_numpy(float)
    y=pd.to_numeric(ref[followup],errors="raise").to_numpy(float); m=mask.to_numpy(bool)
    observed=float(np.mean(y[m]-b[m])); expected=float(np.mean(pred[m]-b[m])); excess=observed-expected
    rng=np.random.default_rng(seed); obs_draw=[]; exp_draw=[]; exc_draw=[]
    for _ in range(bootstrap_draws):
        s=ref.iloc[stratified_indices(ref,bootstrap_strata,rng)].reset_index(drop=True)
        s["calibration_group"]=s["miscalibration_first"].map(calibration_label)
        sm=(s["calibration_group"]!="Accurate") if group=="Miscalibrated" else (s["calibration_group"]==group)
        sm=sm.to_numpy(bool)
        if sm.sum()<2: continue
        sp,_,_=fit(s,baseline,followup,include_tutorial)
        sb=pd.to_numeric(s[baseline],errors="raise").to_numpy(float); sy=pd.to_numeric(s[followup],errors="raise").to_numpy(float)
        o=float(np.mean(sy[sm]-sb[sm])); e=float(np.mean(sp[sm]-sb[sm]))
        obs_draw.append(o); exp_draw.append(e); exc_draw.append(o-e)
    obs_ci=ci(obs_draw); exp_ci=ci(exp_draw); exc_ci=ci(exc_draw)
    prng=np.random.default_rng(seed+1); null=np.empty(permutation_draws,float)
    strata=[np.asarray(v,int) for v in ref.groupby(list(permutation_strata),sort=True).indices.values()]
    for i in range(permutation_draws):
        py=y.copy()
        for idx in strata: py[idx]=prng.permutation(py[idx])
        null[i]=float(np.mean(py[m]-b[m]))
    null_mean=float(null.mean()); null_ci=ci(null); distance=abs(observed-null_mean)
    p2=float((1+np.sum(np.abs(null-null_mean)>=distance))/(len(null)+1))
    pdirectional=float((1+np.sum(null>=observed if observed>=null_mean else null<=observed))/(len(null)+1))
    row={
        "analysis_id":analysis,"outcome":outcome,"group":group,"reference_n":len(ref),"group_n":int(m.sum()),
        "baseline_mean":float(b[m].mean()),"followup_mean":float(y[m].mean()),
        "observed_change_second_minus_first":observed,"observed_change_ci_low":obs_ci[0],"observed_change_ci_high":obs_ci[1],
        "expected_change_under_pooled_rtm_model":expected,"expected_change_ci_low":exp_ci[0],"expected_change_ci_high":exp_ci[1],
        "excess_change_beyond_pooled_rtm":excess,"excess_change_ci_low":exc_ci[0],"excess_change_ci_high":exc_ci[1],
        "baseline_to_followup_slope":slope,"baseline_followup_correlation":corr,
        "permutation_null_mean_change":null_mean,"permutation_null_ci_low":null_ci[0],"permutation_null_ci_high":null_ci[1],
        "permutation_p_two_sided":p2,"permutation_p_directional":pdirectional,
        "bootstrap_draws_completed":len(exc_draw),"permutation_draws":permutation_draws,
        "rtm_compatibility":"Compatible with pooled RTM benchmark" if exc_ci[0]<=0<=exc_ci[1] else "Residual change beyond pooled RTM benchmark",
    }
    if analysis=="H2":
        row.update({
            "observed_improvement_first_minus_second":-observed,
            "expected_improvement_under_pooled_rtm":-expected,
            "excess_improvement_beyond_pooled_rtm":-excess,
            "excess_improvement_ci_low":-exc_ci[1],"excess_improvement_ci_high":-exc_ci[0],
        })
    return row
