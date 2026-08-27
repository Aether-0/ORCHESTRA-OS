# ETH HAI Independent Clean Reimplementation

This directory begins the independent reimplementation of the CHI 2023 study
*Knowing About Knowing*. It is deliberately separated from the direct-reproduction
workflows.

## Current gate

The first gate reconstructs the core data contract and Human–AI reliance metrics without
importing or calling the released `data_analysis/util.py`. It verifies:

- the final analytic sample and four condition sizes;
- the frozen ten task orders;
- ER-008, four correct AI recommendations in each six-task experimental batch;
- first- and second-batch calibration distributions;
- ATI, propensity, trust, Accuracy, Agreement, Switch Fraction, RAIR, and RSR
  descriptive anchors;
- zero-denominator counts for later sensitivity analysis;
- hand-constructed reliance-metric unit tests.

## Integrity boundary

- Raw participant CSV files remain in the private runner checkout.
- Public artifacts contain aggregate outputs only.
- Participant identifiers and participant-level rows are not emitted.
- Direct-reproduction scripts are not edited.
- Robustness alternatives are not mixed into equivalence mode.

## Files

- `core.py` — independent data contract, scoring, and metric engine.
- `test_core.py` — deterministic unit tests.
- `run_clean_core_gate.py` — aggregate equivalence gate.
- `ROBUSTNESS_AUDIT_PLAN.md` — pre-specified sensitivity workstream.
