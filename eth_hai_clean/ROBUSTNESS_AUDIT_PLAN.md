# ETH HAI Clean Reimplementation and Robustness Audit Plan v1.0

## Boundary

The clean reimplementation is separate from the direct reproduction. It will not edit,
patch, or silently substitute the released scripts. The first clean-core gate preserves
the released definitions solely to establish computational equivalence; robustness
variants are introduced only after that gate passes and are labeled explicitly.

## Workstream A — clean, transparent equivalence pipeline

1. **Data contract and inclusion**
   - Validate the two released CSV schemas.
   - Reproduce all-column complete-case filtering and four-attention-check inclusion.
   - Encode the released tutorial mapping explicitly and audit it against study prose.

2. **Task structure**
   - Freeze all ten substantive task orders after attention-check removal.
   - Verify four correct AI recommendations in each six-task experimental batch.
   - Preserve first, intervening, and second task blocks explicitly.

3. **Human–AI metrics**
   - Implement Accuracy, Agreement Fraction, Switch Fraction, Accuracy-wid,
     RAIR, and RSR without importing upstream `util.py`.
   - Unit-test positive/negative AI reliance, positive/negative self-reliance,
     zero denominators, and correct third-option behavior.

4. **Psychometric scores and calibration**
   - Implement ATI, TiA propensity, two trust measurements, and signed calibration.
   - Record scale transformations and reverse-coded items in one data dictionary.

5. **Unified outputs**
   - Generate one aggregate analysis frame and machine-readable result tables.
   - Match direct-reproduction anchors before any robustness alternative is run.
   - Never emit participant identifiers or raw participant rows in public artifacts.

## Workstream B — pre-specified robustness analyses

| ID | Concern | Primary robustness variants | Main outputs |
|---|---|---|---|
| RB-01 | Tutorial coding ambiguity | Released mapping; prose-consistent relabeling check; count reconciliation | Coding decision memo |
| RB-02 | All-column complete-case filtering | Released filter; analysis-specific complete cases | Sample-size and result deltas |
| RB-03 | Undefined RAIR/RSR encoded as zero | Zero; missing/NA; denominator-conditioned analysis | Means, tests, correlations |
| RB-04 | SD convention inconsistency | ddof=0 and ddof=1 | Dual descriptive table |
| RB-05 | Normality script defects | Correct batch extraction; histograms/QQ; Shapiro/Anderson where appropriate | Diagnostic appendix |
| RB-06 | H1 group/outcome coupling | Same-batch reproduction; held-out second-batch outcomes; cross-validated grouping | Association stability |
| RB-07 | Multiplicity family ambiguity | Published alpha=.0125; Bonferroni over six; Holm; BH-FDR | Decision matrix |
| RB-08 | H2 Wilcoxon sensitivity | `wilcox`, `pratt`, `zsplit`; continuity correction; two-sided and directional | p-value grid |
| RB-09 | H2 boundary result | Exact/approximate methods where valid; bootstrap paired differences | Stability of overestimator claim |
| RB-10 | H3 directional tests | Published one-sided; two-sided; direction-agnostic effect sizes | Table 4 sensitivity |
| RB-11 | H3 mixed p-value reporting | Report p-unc and Bonferroni/Holm p values consistently | Corrected Table 5 |
| RB-12 | H4 bounded outcomes and OLS assumptions | HC3 robust SE; permutation tests; bootstrap CIs | Robust Table 7 |
| RB-13 | H4 baseline omission | Second-batch outcome; change score; baseline-adjusted ANCOVA; repeated-measures model | Treatment-effect comparison |
| RB-14 | DKE tied quartile cutoffs | Released stable order; tie-inclusive; repeated random tie-breaks | Distribution of Table 8 estimates |
| RB-15 | DKE same-batch circularity | First-batch grouping/second-batch outcomes; continuous accuracy models | Held-out analysis |
| RB-16 | Trust condition ANCOVA unreported | Verify model; estimated marginal means; corrected pairwise contrasts | Supplementary trust table |
| RB-17 | Trust outcome construction | Mean of two trust waves; second wave with baseline adjustment; change score | Model comparison |
| RB-18 | Task-order heterogeneity | Order fixed effects; clustered/robust analysis; leave-one-order-out | Order sensitivity |
| RB-19 | Precision and package sensitivity | Frozen environment plus current stable stack | Cross-version result matrix |
| RB-20 | Uncertainty reporting | Bootstrap confidence intervals and standardized effect sizes | Robustness appendix |

## Execution order

1. Pass the independent clean-core equivalence gate.
2. Freeze the clean data dictionary and golden aggregate anchors.
3. Implement RB-01 through RB-05 as foundation checks.
4. Run hypothesis-specific audits RB-06 through RB-17.
5. Run order, version, and uncertainty checks RB-18 through RB-20.
6. Produce a result-level concordance table: Published → Direct → Clean → Robustness.

## Decision language

- **Stable:** conclusion unchanged across reasonable alternatives.
- **Specification-sensitive:** conclusion changes under at least one defensible alternative.
- **Source-limited:** required input is unavailable.
- **Exploratory:** not identified as a primary published result or lacks a pre-specified test.

No robustness result will be described as a failure of the original study merely because a
different defensible specification produces a different p-value. The report will separate
computational reproducibility, reporting consistency, and inferential robustness.
