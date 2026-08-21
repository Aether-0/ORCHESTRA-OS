# Findings and diagnosis

## P0 — none

No critical system-stability event occurred. The machine remained responsive, final sched_ext state was disabled, ORCHESTRA pins were absent, and final package temperature was 57 C against an 80 C high and 100 C critical trip point.

## P1-1 — finite positive ownership and forward progress gate not met

Observed symptom: a task started with the existing fixed_work binary, admitted with the existing bridge, and published with RUN did not complete within 20 seconds. The captured status contained the exact published identity but accepted=0 and dispatched=0 for that task. The timeout returned 124 and the task was terminated during cleanup.

Exact reproduction: the logged finite_orchestra_forward_progress command in COMMANDS.log; its stdout is workloads/20260821-095946-finite_orchestra_forward_progress.stdout.

Expected result: the finite workload should complete under the active scheduler, with an exact per-task identity record showing positive ownership and progress. The matched Linux/CFS diagnostic completed the same 10-billion-iteration workload in 5,036 ms; evidence is baseline/20260821-100054-finite_cfs_diagnostic_baseline.stdout.

Actual result: no completion within 20 seconds and no per-task accepted/dispatched telemetry at the captured ownership point. The scheduler was unloaded safely afterward. No kernel error or sched_ext error accompanied the timeout.

Earliest failing layer: ownership/observability gate. The result must be classified INCONCLUSIVE_OWNERSHIP_NOT_PROVEN rather than attributed to an ORCHESTRA performance result.

Most likely causes: an admission-to-task-lifecycle race in this launch protocol; the identity record was published after the task's relevant enable/enqueue point; or the full-switch fallback path did not provide the expected task progress. A workload-size/timeout or harness interaction is an alternative explanation, although CFS completed the matched workload well inside the limit. Confidence in the observed symptom is HIGH; confidence in the root cause is LOW.

How to verify: repeat only after an existing safe protocol can poll for the exact task record and positive accepted/enqueue/running evidence before timing the finite workload; correlate that record with per-task enable/enqueue/running counters and the task's processor field. Do not infer ownership from the publication return code or global counters.

Recommended correction, not applied: make the existing ownership gate establish and observe the exact live-TID admission/enqueue state before performance timing, then investigate the kernel enable/enqueue path if the same exact-TID protocol still yields zero accepted/dispatched records. Add no source change during this campaign.

## P2-1 — SLEEP is only partially validated

The valid timeline produced deferred=2 and deferred_release=2 after future deadlines, with no deferred release failures. However, the early snapshot did not independently measure task CPU time or an equivalent no-early execution invariant. After the deadline, later enqueues of the unchanged one-shot SLEEP directive increased fallback counts and reported fallback reason 9, bad parameters. The implementation explicitly rejects an expired not_before value in orchestra_scx_stage7.bpf.c lines 563-568.

Recommended correction, not applied: define and expose one-shot directive lifecycle/clear semantics or continuously refresh the directive, then repeat with an independent no-early execution measurement.

## P2-2 — comparable performance and ORCHESTRA stress coverage is blocked

perf and scx_simple are missing. benchmark_suite.sh and full_compare.sh assume /home/vagrant paths and contain broad link/pin cleanup paths; they were not executed. stress_suite.sh can run a safe CFS phase, but its orchestra mode only checks sched_ext state and does not opt tasks in, so it cannot establish an ORCHESTRA result. The three-second CFS smoke passed all workload phases and emitted one false-positive health warning because its grep matched pre-existing ACPI BIOS lines.

Recommended correction, not applied: provide a location-independent, ownership-validating benchmark path and review cleanup scope; install optional tools only with separate user approval.

## P2-3 — research-stage kernel features are not implemented in this revision

Source inspection found the stage7 scheduler, bridge ABI, lifecycle callbacks, task state, action maps, telemetry, and five canonical actions. It did not find an executable kernel signal bus with authenticated predictive frames, a kernel predictor, kernel S1/S2/S3/S4/Q, a feedback controller, full hybrid RT bypass, NUMA policy, or distributed coordination. Passing userspace HMAC, predictor, coordination, controller, and tamper tests does not upgrade these to kernel or real-machine claims.

Recommended correction, not applied: implement and separately instrument each missing layer before scheduling it into a real-machine acceptance campaign.

## P2-4 — topology and observability limit the claim boundary

This host has one NUMA node and one machine; it cannot validate cross-node or distributed behavior. The kernel prototype exposes useful per-task/global counters but not enough causal evidence for all architectural metrics. No S1/S2/S3/S4/Q was reported, because the required signal fidelity, compliance, coherence, and temporal stability inputs are not exposed by this runtime.

Recommended correction, not applied: add explicit measurement definitions and causal event sources before reporting coordination or scalability metrics.

## P3-1 — first baseline harness attempts produced malformed CSV

The first two baseline collection attempts at baseline/20260821-094845-baseline_fixed_work.stdout and baseline/20260821-094909-baseline_fixed_work_retry.stdout had formatting/load-average field errors. They were preserved, diagnosed, and not used for results. The corrected third attempt at baseline/20260821-094943-baseline_fixed_work_retry2.stdout produced 12 valid rows.

Recommended correction, not applied: fix the external evidence-collection formatting before reuse; no repository source or test file was changed.
