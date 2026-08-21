# ORCHESTRA-OS real-machine campaign status

Status: COMPLETE_WITH_INCONCLUSIVE_AND_BLOCKED_ITEMS

Campaign: real-machine-20260821-094227-kali-2qqYxp

Repository commit: 07c787c4eeac01a2f9d60916577806d00863b15f

Host: kali; kernel 7.0.12+kali-amd64

Final sched_ext state: disabled

Runtime result: the fresh stage7 BPF object loaded three times through the existing map-pinning loader and unloaded three times. RUN, YIELD, MIGRATE, fallback, and THROTTLE telemetry were observed for a controlled task. SLEEP deferred/release telemetry was observed but no-early execution was not independently proven. A finite 10-billion-iteration positive worker did not complete within 20 seconds and had no accepted/dispatched per-task records at the captured ownership point; this stopped further runtime escalation.

Build result: userspace and fresh out-of-tree BPF/bridge/loader/workload builds passed.

Coverage boundary: kernel signal bus, predictor, kernel S1/S2/S3/S4/Q, feedback controller, full hybrid RT safety, NUMA-aware logic, and distributed scheduling were not executable features in this revision.

DOCX checklist audit: 519 items mapped in CHECKLIST_AUDIT.csv and summarized in CHECKLIST_COVERAGE.md; 94 PASS, 39 INCONCLUSIVE, 178 BLOCKED, 208 NOT IMPLEMENTED.

Evidence index: COMMANDS.log, CHECKLIST_STATUS.csv, TEST_RESULTS.csv, RESULTS.json, FINDINGS.md, EXECUTIVE_SUMMARY.md, and the timestamped final report in this directory.

Tracked-source integrity: final git diff is empty. The campaign directory and pre-existing untracked artifacts remain unmodified.
