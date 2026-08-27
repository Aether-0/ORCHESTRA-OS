from __future__ import annotations
from typing import Dict,List
import numpy as np
import pandas as pd
from eth_hai_extension.core import POLICIES,PRIMARY_NUMERIC_FEATURES,PRIMARY_CATEGORICAL_FEATURES,policy_assignments
from eth_hai_extension.estimators import fit_cross_fitted_nuisance,policy_value_aipw

def ratio_count_rows(frame:pd.DataFrame)->List[Dict[str,object]]:
    assignments=policy_assignments(frame); rows=[]
    specs={"RAIR":("second_positive_ai_reliance","second_negative_self_reliance","outcome_second_rair_defined"),
           "RSR":("second_positive_self_reliance","second_negative_ai_reliance","outcome_second_rsr_defined")}
    for ratio,(num_col,fail_col,defined_col) in specs.items():
        opp_col="_opportunity_"+ratio.lower(); frame[opp_col]=pd.to_numeric(frame[num_col])+pd.to_numeric(frame[fail_col])
        nfit=fit_cross_fitted_nuisance(frame,num_col,PRIMARY_NUMERIC_FEATURES,PRIMARY_CATEGORICAL_FEATURES)
        ofit=fit_cross_fitted_nuisance(frame,opp_col,PRIMARY_NUMERIC_FEATURES,PRIMARY_CATEGORICAL_FEATURES)
        yn=pd.to_numeric(frame[num_col]).to_numpy(float); yo=pd.to_numeric(frame[opp_col]).to_numpy(float); a=frame["treatment"].to_numpy(int)
        for policy in POLICIES:
            d=assignments[policy.policy_id].to_numpy(int)
            n=policy_value_aipw(yn,a,d,nfit["propensity"],nfit["m0"],nfit["m1"])
            o=policy_value_aipw(yo,a,d,ofit["propensity"],ofit["m0"],ofit["m1"])
            rows.append({"ratio":ratio,"policy_id":policy.policy_id,"policy_name":policy.name,"coverage_fraction":float(d.mean()),
            "standardized_numerator_count_per_participant":n.policy_value,"standardized_opportunity_count_per_participant":o.policy_value,
            "opportunity_pooled_ratio":float(n.policy_value/o.policy_value),"observed_total_numerator":int(yn.sum()),
            "observed_total_opportunities":int(yo.sum()),"defined_participant_n":int(pd.to_numeric(frame[defined_col],errors="coerce").notna().sum())})
    return rows
