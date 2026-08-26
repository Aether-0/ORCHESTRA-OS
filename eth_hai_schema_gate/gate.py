#!/usr/bin/env python3
"""Pre-analysis gate: source schema/encoding validation and hand-built reliance tests.

Outputs aggregate metadata only. It does not run any paper analysis script and does not
emit participant rows or participant identifiers.
"""
from __future__ import annotations

import argparse, contextlib, hashlib, importlib.util, io, json, math, sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

import numpy as np
import pandas as pd

COMMIT = "008f9833ab8c4c23ed94908e0108053a2240a100"
N = 249
TASK_IDS = [0,1,2,3,4,5,7,8,9,10,12,13,14,15,16,17]
ATTN_IDS = [6,11,18]
CHOICES = {"A","B","C","D"}
ALL_COLS = (["ai_id","username","user_id","task_counter","tutorial","XAI","question_order","previous"]
            + [f"question{i}" for i in TASK_IDS] + [f"advice{i}" for i in TASK_IDS]
            + ["attention_ati","attention6","attention11","attention18"]
            + [f"ati{i}" for i in range(1,10)] + [f"pt{i}" for i in range(1,4)]
            + ["tia1_1","tia1_2","tia2_1","tia2_2"]
            + ["surveySelf1","surveySelf2","surveyOther1","surveyOther2",
               "surveyPercentage1","surveyPercentage2","xai_question"])
TASK_COLS = ["context","question","answers/0","answers/1","answers/2","answers/3",
             "label","answer","id_string","AI-advice","tutorialA","tutorialB","tutorialC","tutorialD"]


def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""): h.update(b)
    return h.hexdigest()


def tsv(path: Path, header: Sequence[str], rows: Iterable[Sequence[Any]]) -> None:
    with path.open("w",encoding="utf-8",newline="\n") as f:
        f.write("\t".join(header)+"\n")
        for row in rows:
            f.write("\t".join(("" if x is None else str(x)).replace("\t"," ").replace("\n"," ").replace("\r"," ") for x in row)+"\n")


def load_util(repo: Path):
    p=repo/"data_analysis"/"util.py"
    s=importlib.util.spec_from_file_location("eth_hai_gate_util",p)
    if s is None or s.loader is None: raise RuntimeError(f"Cannot import {p}")
    m=importlib.util.module_from_spec(s); sys.dont_write_bytecode=True; s.loader.exec_module(m)
    m.data_folder=str(repo/"anonymous_data")
    return m


def close(a: float,b: float,tol: float=1e-12):
    if not math.isclose(float(a),float(b),rel_tol=tol,abs_tol=tol):
        raise AssertionError(f"{a!r} != {b!r}")


def exact(a: Any,b: Any):
    if a!=b: raise AssertionError(f"{a!r} != {b!r}")


def fixture(rows: Sequence[Dict[str,str]]):
    user="Synthetic_User"; ud={user:{}}; ad={}; ids=[]
    for i,r in enumerate(rows):
        ids.append(i); ud[user][(i,"base")]=r["initial"]; ud[user][(i,"advice")]=r["final"]
        ad[i]=(r["correct"],r["ai"],f"synthetic_{i}")
    return user,ud,ad,ids


def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--repo",type=Path,required=True); ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args(); repo=a.repo.resolve(); out=a.out.resolve(); out.mkdir(parents=True,exist_ok=True)
    checks: List[Dict[str,Any]]=[]
    def ck(cid,cat,status,observed,expected,note=""):
        checks.append({"id":cid,"category":cat,"status":status,"observed":observed,"expected":expected,"note":note})

    pp=repo/"anonymous_data"/"all_valid_data.csv"; tp=repo/"anonymous_data"/"selected_samples.csv"
    enc=[]
    for p in [pp,tp]:
        raw=p.read_bytes(); ok=True; err=""
        try: raw.decode("utf-8-sig")
        except UnicodeDecodeError as e: ok=False; err=repr(e)
        enc.append([str(p.relative_to(repo)),len(raw),sha256(p),raw.startswith(b"\xef\xbb\xbf"),ok,err])
        ck(f"utf8.{p.name}","encoding","PASS" if ok else "FAIL",ok,True)
    d=pd.read_csv(pp,encoding="utf-8-sig"); q=pd.read_csv(tp,encoding="utf-8-sig")
    ck("participant.rows","schema","PASS" if len(d)==N else "FAIL",len(d),N)
    ck("participant.columns","schema","PASS" if list(d.columns)==ALL_COLS else "FAIL",list(d.columns),ALL_COLS)
    ck("task.rows","schema","PASS" if len(q)==19 else "FAIL",len(q),19)
    ck("task.columns","schema","PASS" if list(q.columns)==TASK_COLS else "FAIL",list(q.columns),TASK_COLS)
    ck("participant.missing","completeness","PASS" if int(d.isna().sum().sum())==0 else "FAIL",int(d.isna().sum().sum()),0)
    ck("participant.username_unique","identity","PASS" if d.username.nunique()==N else "FAIL",int(d.username.nunique()),N,"No IDs are emitted.")
    ck("task_counter","domain","PASS" if set(d.task_counter.astype(int))=={19} else "FAIL",sorted(set(d.task_counter.astype(int))),[19])
    for c in ["tutorial","XAI"]:
        v=sorted(set(d[c].astype(int))); ck(f"binary.{c}","encoding","PASS" if v==[0,1] else "FAIL",v,[0,1])
    qo=sorted(set(d.question_order.astype(int))); ck("question_order.domain","encoding","PASS" if qo==list(range(10)) else "FAIL",qo,list(range(10)))
    bad={}
    for c in [f"question{i}" for i in TASK_IDS]+[f"advice{i}" for i in TASK_IDS]:
        x=sorted(set(d[c].astype(str))-CHOICES)
        if x: bad[c]=x
    ck("decision.values","domain","PASS" if not bad else "FAIL",bad,{})

    domains=[]; ranges={}
    for c in [f"ati{i}" for i in range(1,10)]: ranges[c]=(0,5)
    for c in [f"pt{i}" for i in range(1,4)]: ranges[c]=(0,4)
    for c in ["surveySelf1","surveySelf2","surveyOther1","surveyOther2"]: ranges[c]=(0,6)
    for c in ["surveyPercentage1","surveyPercentage2"]: ranges[c]=(0,100)
    for c in ["tutorial","XAI","question_order","attention_ati",*[f"ati{i}" for i in range(1,10)],
              *[f"pt{i}" for i in range(1,4)],"tia1_1","tia1_2","tia2_1","tia2_2",
              "surveySelf1","surveySelf2","surveyOther1","surveyOther2","surveyPercentage1","surveyPercentage2","xai_question"]:
        s=pd.to_numeric(d[c],errors="coerce"); lo=float(s.min()); hi=float(s.max())
        domains.append([c,lo,hi,int(s.nunique()),int(s.isna().sum())])
        if c in ranges:
            e=ranges[c]; ck(f"range.{c}","domain","PASS" if lo>=e[0] and hi<=e[1] else "FAIL",[lo,hi],list(e))

    att=((pd.to_numeric(d.attention_ati)==3).astype(int)+(d.attention6.astype(str)=="B").astype(int)
         +(d.attention11.astype(str)=="D").astype(int)+(d.attention18.astype(str)=="C").astype(int))
    adist={str(k):int(v) for k,v in sorted(Counter(att.astype(int)).items())}
    ck("attention.participants","attention","PASS" if bool((att==4).all()) else "FAIL",adist,{"4":N})
    ck("tasks.id_unique","identity","PASS" if q.id_string.nunique()==19 else "FAIL",int(q.id_string.nunique()),19)
    amap={0:"A",1:"B",2:"C",3:"D"}; mm=sum(amap.get(int(x))!=str(y) for x,y in zip(q.label,q.answer))
    ck("tasks.label_answer","encoding","PASS" if mm==0 else "FAIL",int(mm),0)
    exp_att={6:("attention_1","B"),11:("attention_2","D"),18:("attention_3","C")}
    obs_att={i:(str(q.loc[i,"id_string"]),str(q.loc[i,"answer"])) for i in ATTN_IDS}
    ck("tasks.attention_rows","attention","PASS" if obs_att==exp_att else "FAIL",obs_att,exp_att)
    non=q.loc[~q.index.isin(ATTN_IDS)]
    inva=sorted(set(non["answer"].astype(str))-CHOICES); invi=sorted(set(non["AI-advice"].astype(str))-CHOICES)
    ck("tasks.answers","domain","PASS" if not inva else "FAIL",inva,[])
    ck("tasks.ai_advice","domain","PASS" if not invi else "FAIL",invi,[])
    ai_correct=int((non.answer.astype(str)==non["AI-advice"].astype(str)).sum())
    ck("tasks.ai_accuracy","aggregate","INFO",[ai_correct,len(non)],"record only")

    util=load_util(repo)
    order_rows=[]; oe=[]; counts=Counter(d.question_order.astype(int))
    for k in sorted(util.question_order_dict):
        seq=[int(x) for x in util.question_order_dict[k]]
        if len(seq)!=16 or len(set(seq))!=16 or set(seq)!=set(TASK_IDS): oe.append({"order":k,"sequence":seq})
        order_rows.append([k,int(counts[k]),",".join(map(str,seq[:6])),",".join(map(str,seq[6:-6])),",".join(map(str,seq[-6:]))])
    ck("question_order.structure","encoding","PASS" if not oe else "FAIL",oe,[])
    with contextlib.redirect_stdout(io.StringIO()):
        valid,approved=util.find_valid_users("all_valid_data.csv",4)
        cond=util.get_user_conditions("all_valid_data.csv",valid)
    ck("upstream.valid_users","upstream_logic","PASS" if len(valid)==N else "FAIL",len(valid),N)
    mapping={(1,0):"no tutorial, no xai",(0,0):"with tutorial, no xai",(1,1):"no tutorial, with xai",(0,1):"with tutorial, with xai"}
    pair=d.groupby(["tutorial","XAI"]).size().to_dict(); condrows=[]
    for raw,label in mapping.items(): condrows.append([raw[0],raw[1],label,int(pair.get(raw,0)),len(cond[label])])
    ck("condition.counts","encoding","PASS" if all(r[3]==r[4] for r in condrows) else "FAIL",{x:len(y) for x,y in cond.items()},{r[2]:r[3] for r in condrows})
    ck("tutorial.semantic_direction","encoding","WARN",{"1":"no tutorial","0":"with tutorial"},"preserve for direct reproduction","README does not explicitly resolve the binary direction; clean reimplementation must justify it independently.")
    x0=int(((d.XAI.astype(int)==0)&(pd.to_numeric(d.xai_question)!=-1)).sum())
    x1=pd.to_numeric(d.loc[d.XAI.astype(int)==1,"xai_question"]); x1bad=int((~x1.between(0,4)).sum())
    ck("xai.sentinel","encoding","PASS" if x0==0 else "FAIL",x0,0)
    ck("xai.helpfulness","encoding","PASS" if x1bad==0 else "FAIL",x1bad,0)

    tests=[]
    def test(name,fn):
        try: fn(); tests.append([name,"PASS",""])
        except Exception as e: tests.append([name,"FAIL",repr(e)])
    rows=[
      {"case":"positive_ai","correct":"A","ai":"A","initial":"B","final":"A"},
      {"case":"negative_self","correct":"A","ai":"A","initial":"B","final":"B"},
      {"case":"positive_self","correct":"A","ai":"B","initial":"A","final":"A"},
      {"case":"negative_ai","correct":"A","ai":"B","initial":"A","final":"B"},
      {"case":"agree_correct","correct":"A","ai":"A","initial":"A","final":"A"},
      {"case":"third_option_correct","correct":"A","ai":"B","initial":"C","final":"A"},
      {"case":"both_wrong_insist","correct":"A","ai":"B","initial":"C","final":"C"},
      {"case":"agree_then_leave","correct":"A","ai":"A","initial":"A","final":"B"},]
    fx=fixture(rows)
    def canonical():
        r=util.calc_user_reliance_measures(*fx); exact(r[0],4); close(r[1],3/8); close(r[2],2/6); close(r[3],3/6); exact(r[4],6); close(r[5],.5); close(r[6],.5)
    test("canonical_calc",canonical)
    def canonical2():
        r=util.analysis_user_reliance_measures(*fx); exact(r[0],4); exact(r[1],3); close(r[2],2/6); exact(r[3],[6,2,3]); exact(r[4],[1,1,1,1]); close(r[5][0],.5); close(r[5][1],.5)
    test("canonical_analysis_variant",canonical2)
    def one(row): return util.calc_user_reliance_measures(*fixture([row]))
    def zero():
        r=one({"correct":"A","ai":"A","initial":"A","final":"A"}); exact(r[0],1); close(r[1],1); close(r[2],0); close(r[3],0); exact(r[4],0); close(r[5],0); close(r[6],0)
    test("zero_denominators",zero)
    def third():
        r=one({"correct":"A","ai":"B","initial":"C","final":"A"}); exact(r[0],1); close(r[1],0); close(r[2],0); close(r[3],1); exact(r[4],1); close(r[5],0); close(r[6],0)
    test("third_option_behavior",third)
    def miscal():
        p=util.UserPerformance("Synthetic_User",[0]); p.add_miscalibration(5,3,"first_group"); p.add_miscalibration(2,4,"second_group"); exact(p.miscalibration["first_group"],2); exact(p.miscalibration["second_group"],-2)
    test("miscalibration_sign",miscal)
    patterns=[
      ("positive_ai",{"correct":"A","ai":"A","initial":"B","final":"A"},[1,1,1,1,1,1,0]),
      ("negative_self",{"correct":"A","ai":"A","initial":"B","final":"B"},[0,0,0,0,1,0,0]),
      ("positive_self",{"correct":"A","ai":"B","initial":"A","final":"A"},[1,0,0,1,1,0,1]),
      ("negative_ai",{"correct":"A","ai":"B","initial":"A","final":"B"},[0,1,1,0,1,0,0])]
    for name,row,e in patterns:
        def f(row=row,e=e):
            r=one(row); exact(r[0],e[0]); close(r[1],e[1]); close(r[2],e[2]); close(r[3],e[3]); exact(r[4],e[4]); close(r[5],e[5]); close(r[6],e[6])
        test(name,f)

    tpass=sum(x[1]=="PASS" for x in tests); tfail=len(tests)-tpass
    sc=Counter(x["status"] for x in checks); fail=sc["FAIL"]+tfail; passed=fail==0
    report={"schema_version":"1.0","generated_at_utc":datetime.now(timezone.utc).isoformat(),
            "repository":"RichardHGL/CHI2023_DKE","pinned_commit":COMMIT,"passed":passed,
            "schema_checks":dict(sc),"metric_tests":{"total":len(tests),"passed":tpass,"failed":tfail},
            "participant_rows":len(d),"task_rows":len(q),"condition_counts":{x:len(y) for x,y in cond.items()},
            "attention_distribution":adist,"ai_advice_task_accuracy":{"correct":ai_correct,"total":len(non)},
            "statistical_scripts_executed":False,"participant_level_data_emitted":False,"checks":checks,"tests":[{"name":x[0],"status":x[1],"error":x[2]} for x in tests],
            "semantic_notes":["Direct reproduction preserves util.py's inverted-looking tutorial mapping.","Zero-denominator reliance ratios return 0.0.","appropriate_reliance is final correctness conditional on initial disagreement; a third-option correction can count without entering RAIR or RSR."]}
    (out/"schema_metric_gate_report.json").write_text(json.dumps(report,indent=2,sort_keys=True,default=str)+"\n",encoding="utf-8")
    tsv(out/"schema_checks.tsv",["id","category","status","observed","expected","note"],[[x["id"],x["category"],x["status"],json.dumps(x["observed"],sort_keys=True,default=str),json.dumps(x["expected"],sort_keys=True,default=str),x["note"]] for x in checks])
    tsv(out/"source_encoding.tsv",["path","bytes","sha256","utf8_bom","decode_ok","error"],enc)
    tsv(out/"condition_counts.tsv",["raw_tutorial","raw_XAI","util_label","raw_count","util_count"],condrows)
    tsv(out/"question_order_counts.tsv",["order","participants","first_6","middle_4","last_6"],order_rows)
    tsv(out/"value_domains.tsv",["field","min","max","unique","missing"],domains)
    tsv(out/"reliance_metric_tests.tsv",["test","status","error"],tests)
    cross=[]
    for r in rows:
        disag=r["initial"]!=r["ai"]; agree=r["final"]==r["ai"]; insist=r["final"]==r["initial"]; correct=r["final"]==r["correct"]
        cat="none"
        if disag and r["ai"]==r["correct"]: cat="positive_ai_reliance" if agree else "negative_self_reliance"
        elif disag and r["ai"]!=r["correct"] and r["initial"]==r["correct"]: cat="positive_self_reliance" if correct else "negative_ai_reliance"
        cross.append([r["case"],r["correct"],r["ai"],r["initial"],r["final"],disag,agree,insist,correct,cat])
    tsv(out/"metric_semantics_crosswalk.tsv",["case","correct","ai","initial","final","disagreement","agrees_ai","insists","final_correct","pattern"],cross)
    md=["# ETH HAI Schema, Encoding & Metric Gate","",f"- Overall: **{'PASS' if passed else 'FAIL'}**",f"- Schema checks: **{sc['PASS']} PASS**, **{sc['FAIL']} FAIL**, **{sc['WARN']} WARN**, **{sc['INFO']} INFO**",f"- Reliance tests: **{tpass}/{len(tests)} passed**","- Participant-level rows or IDs emitted: **No**","- Statistical scripts executed: **No**","","## Required interpretation notes","","- Direct reproduction preserves `util.py`: raw `tutorial=1` is labeled **no tutorial**, and raw `tutorial=0` is labeled **with tutorial**. The repository README does not explicitly resolve the binary direction.","- Zero-denominator reliance ratios return `0.0`.","- `appropriate_reliance` is final correctness conditional on initial disagreement; a correct third-option response can count while contributing to neither RAIR nor RSR."]
    (out/"GATE_STATUS.md").write_text("\n".join(md)+"\n",encoding="utf-8")
    print(json.dumps({"passed":passed,"schema":dict(sc),"metric_tests":{"passed":tpass,"total":len(tests)},"out":str(out)},indent=2,sort_keys=True))
    return 0 if passed else 1

if __name__=="__main__": raise SystemExit(main())
