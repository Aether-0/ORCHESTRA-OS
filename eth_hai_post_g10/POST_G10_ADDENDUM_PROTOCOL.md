# Post-G10 Methodological Addendum Protocol v1.0

**Registered:** 2026-08-27, before viewing post-G10 addendum outputs  
**Reviewer basis:** G10 External Methodological Review Report  
**Status:** Separately versioned addendum; frozen direct, robustness, and policy registers remain unchanged

## Purpose

Address the reviewer's concerns about (1) regression toward the mean after selection on a noisy Batch-1 measure, (2) attainable precision of the three primary policy contrasts, and (3) numerator/opportunity transparency for RAIR and RSR.

## A1. Regression-to-the-mean diagnostic

For H2, among observed tutorial participants, fit a pooled linear follow-up model for Batch-2 absolute calibration gap using Batch-1 absolute calibration gap, XAI, and task-order indicators. Compare observed change with model-expected change for all initially miscalibrated participants, underestimators, and overestimators.

For H3, fit a pooled follow-up model separately for Accuracy, Agreement Fraction, Switch Fraction, Accuracy-wid, RAIR, and RSR using the corresponding Batch-1 outcome, tutorial, XAI, and task-order indicators. Compare observed and expected changes for Batch-1 underestimators and overestimators.

Report:
- baseline and follow-up means;
- observed change;
- expected change under the pooled regression benchmark;
- excess change beyond the benchmark;
- 5,000-draw stratified bootstrap intervals;
- 10,000-draw stratified permutation-null distribution.

Interpretation is diagnostic, not causal. Compatibility with the benchmark does not prove RTM is the sole explanation; it shows that specification robustness does not rule out selection-on-baseline artifacts.

## A2. Split-half feasibility

Do not invent a split-specific self-assessment. The source contains one self-assessment for the complete six-task Batch 1. Record the split-half analysis as not performed unless a defensible split-specific self-assessment becomes available.

## A3. Precision and MDE

Using the frozen normal standard errors for P01, P03, and P05 versus P07, calculate 80% power minimum detectable contrasts under:
- two-sided alpha .05;
- Holm first-step alpha .05/3;
- source fixed alpha .0125.

Report the universal-versus-none anchor (+0.097149) for scale and an approximate same-variance sample size required to detect an anchor-sized contrast.

## A4. RAIR and RSR count transparency

For P00-P07, report model-standardized numerator counts per participant, model-standardized opportunity counts per participant, opportunity-pooled ratios, observed aggregate numerator/opportunity totals, and defined-participant N.

## Integrity controls

- Use the pinned source commit `008f9833ab8c4c23ed94908e0108053a2240a100` and root tree `2ba7a4f41807de9a32670f77d55598fabcb253d9`.
- Reuse the exact CPython 3.8.16 frozen environment.
- Execute twice with deterministic aggregate outputs.
- Emit no participant-level row or identifier.
- Make no causal-identification claim.
- Do not alter any frozen register or earlier classification.
