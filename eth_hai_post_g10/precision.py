from __future__ import annotations
from typing import Dict,List
from scipy import stats

ANCHOR=0.09714901813831814
CONTRASTS=(
("P01","Underestimators only",-0.008597513662071656,0.1123375656374268,-0.22877509642233254,0.21158006909818924),
("P03","Overestimators only",-0.10833635909415831,0.11621576810529421,-0.3361150790161937,0.11944236082787707),
("P05","All miscalibrated",-0.019740383068964577,0.07489915612532302,-0.1665400315470403,0.12705926540911114),)

def mde_rows(power:float=.80)->List[Dict[str,object]]:
    zpow=float(stats.norm.ppf(power)); rows=[]
    for pid,name,est,se,lo,hi in CONTRASTS:
        for rule,alpha in (("Two-sided alpha .05",.05),("Holm first-step alpha .05/3",.05/3),("Source fixed alpha .0125",.0125)):
            mde=float((stats.norm.ppf(1-alpha/2)+zpow)*se); multiple=mde/abs(ANCHOR)
            rows.append({"policy_id":pid,"policy_name":name,"observed_estimate":est,"normal_standard_error":se,
            "normal_ci_low":lo,"normal_ci_high":hi,"alpha_rule":rule,"two_sided_alpha":alpha,"power":power,
            "minimum_detectable_contrast":mde,"universal_vs_none_anchor":ANCHOR,"mde_as_multiple_of_anchor":multiple,
            "approximate_n_to_detect_anchor_same_variance":249*multiple*multiple})
    return rows
