#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from typing import Dict,List,Mapping,Sequence
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from eth_hai_clean.core import build_clean_metric_frame
from eth_hai_extension.core import build_extension_frame
from eth_hai_post_g10.io_utils import write_json,write_tsv
from eth_hai_post_g10.rtm import benchmark,calibration_label
from eth_hai_post_g10.precision import mde_rows,ANCHOR
from eth_hai_post_g10.ratio_counts import ratio_count_rows

FIELDS=["analysis_id","outcome","group","reference_n","group_n","baseline_mean","followup_mean",
"observed_change_second_minus_first","observed_change_ci_low","observed_change_ci_high",
"expected_change_under_pooled_rtm_model","expected_change_ci_low","expected_change_ci_high",
"excess_change_beyond_pooled_rtm","excess_change_ci_low","excess_change_ci_high",
"observed_improvement_first_minus_second","expected_improvement_under_pooled_rtm",
"excess_improvement_beyond_pooled_rtm","excess_improvement_ci_low","excess_improvement_ci_high",
"baseline_to_followup_slope","baseline_followup_correlation","permutation_null_mean_change",
"permutation_null_ci_low","permutation_null_ci_high","permutation_p_two_sided","permutation_p_directional",
"bootstrap_draws_completed","permutation_draws","rtm_compatibility"]

def plot_rtm(rows:Sequence[Mapping[str,object]],path:Path):
    labels=[f"{r['analysis_id']}\n{r['outcome']}\n{r['group']}" for r in rows]; x=np.arange(len(labels)); w=.38
    fig,ax=plt.subplots(figsize=(max(12,len(labels)*.68),7)); ax.bar(x-w/2,[r["observed_change_second_minus_first"] for r in rows],w,label="Observed")
    ax.bar(x+w/2,[r["expected_change_under_pooled_rtm_model"] for r in rows],w,label="RTM benchmark"); ax.axhline(0,lw=1)
    ax.set_xticks(x); ax.set_xticklabels(labels,rotation=55,ha="right",fontsize=8); ax.set_ylabel("Second minus first"); ax.legend(); fig.tight_layout(); fig.savefig(path,dpi=200,bbox_inches="tight"); plt.close(fig)

def plot_mde(rows,path):
    f=[r for r in rows if r["alpha_rule"]=="Holm first-step alpha .05/3"]; x=np.arange(3); w=.38
    fig,ax=plt.subplots(figsize=(8,5.5)); ax.bar(x-w/2,[r["minimum_detectable_contrast"] for r in f],w,label="80% MDE")
    ax.bar(x+w/2,[abs(r["observed_estimate"]) for r in f],w,label="Observed |contrast|"); ax.axhline(abs(ANCHOR),ls="--",label="Universal-vs-none anchor")
    ax.set_xticks(x); ax.set_xticklabels([r["policy_id"] for r in f]); ax.set_ylabel("Calibration-improvement points"); ax.legend(); fig.tight_layout(); fig.savefig(path,dpi=200,bbox_inches="tight"); plt.close(fig)

def main():
    p=argparse.ArgumentParser(); p.add_argument("--repo",type=Path,required=True); p.add_argument("--out",type=Path,required=True)
    p.add_argument("--bootstrap-draws",type=int,default=5000); p.add_argument("--permutation-draws",type=int,default=10000); p.add_argument("--no-figures",action="store_true"); a=p.parse_args()
    out=a.out.resolve(); out.mkdir(parents=True,exist_ok=True); clean=build_clean_metric_frame(a.repo.resolve(),"zero").reset_index(drop=True)
    clean["calibration_group"]=clean["miscalibration_first"].map(calibration_label); clean["abs_miscalibration_first"]=clean["miscalibration_first"].abs(); clean["abs_miscalibration_second"]=clean["miscalibration_second"].abs()
    rows:List[Dict[str,object]]=[]; tutorial=clean[clean["tutorial_raw"]==0].reset_index(drop=True)
    for group in ("Miscalibrated","Underestimation","Overestimation"):
        rows.append(benchmark(tutorial,group,"abs_miscalibration_first","abs_miscalibration_second","H2","Absolute calibration gap",False,("xai_raw",),("xai_raw",),a.bootstrap_draws,a.permutation_draws,20260827+len(rows)*100))
    outcomes=(("Accuracy","first_accuracy","second_accuracy"),("Agreement Fraction","first_agreement_fraction","second_agreement_fraction"),("Switch Fraction","first_switch_fraction","second_switch_fraction"),("Accuracy-wid","first_appropriate_reliance","second_appropriate_reliance"),("RAIR","first_rair","second_rair"),("RSR","first_rsr","second_rsr"))
    for label,b,f in outcomes:
        for group in ("Underestimation","Overestimation"):
            rows.append(benchmark(clean,group,b,f,"H3",label,True,("tutorial_raw","xai_raw"),("tutorial_raw","xai_raw"),a.bootstrap_draws,a.permutation_draws,20260827+len(rows)*100))
    write_tsv(out/"post_g10_rtm_benchmarks.tsv",rows,FIELDS); mde=mde_rows(); write_tsv(out/"post_g10_primary_mde.tsv",mde)
    ratios=ratio_count_rows(build_extension_frame(a.repo.resolve())); write_tsv(out/"post_g10_ratio_counts.tsv",ratios)
    split={"status":"Not performed","reason":"Only one self-assessment exists for the full six-task Batch 1; no split-specific self-assessment exists.","existing_related_evidence":"RB-06 and RB-15 use Batch 2 held-out outcomes but do not remove RTM from within-group change.","recommended_future_design":"Collect split-specific or trial-level confidence and separate grouping from evaluation."}; write_json(out/"post_g10_split_half_feasibility.json",split)
    if not a.no_figures: plot_rtm(rows,out/"post_g10_rtm_observed_vs_expected.png"); plot_mde(mde,out/"post_g10_primary_mde.png")
    summary={"schema_version":"1.0","sample_n":len(clean),"tutorial_n":len(tutorial),"bootstrap_draws":a.bootstrap_draws,"permutation_draws":a.permutation_draws,"rtm_rows_n":len(rows),"mde_rows_n":len(mde),"ratio_count_rows_n":len(ratios),"frozen_registers_modified":False,"participant_level_data_emitted":False,"causal_identification_claimed":False,"split_half_performed":False,"h2":[r for r in rows if r["analysis_id"]=="H2"],"h3_underestimation":[r for r in rows if r["analysis_id"]=="H3" and r["group"]=="Underestimation"]}; write_json(out/"post_g10_addendum_summary.json",summary)
    (out/"POST_G10_STATUS.md").write_text("# Post-G10 RTM and Precision Addendum\n\n- Execution: **PASS**\n- Frozen registers modified: **NO**\n- Participant-level data emitted: **NO**\n- Split-half analysis: **NOT PERFORMED — source lacks split-specific self-assessment**\n",encoding="utf-8")
    print(json.dumps({"passed":True,"rtm_rows":len(rows),"mde_rows":len(mde),"ratio_rows":len(ratios)},sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
