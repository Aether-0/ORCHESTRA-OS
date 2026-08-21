# Findings and root-cause analysis

## P0 — none

No kernel panic, unrecoverable lockup, data loss, thermal safety event, or unload failure occurred. Final state is disabled, ORCHESTRA pins/links/maps/programs are absent, and the final package temperature was about 48°C against an 80°C high and 100°C critical trip point.

## F-001 — persistent multi-worker ownership gate failures

FINDING ID: F-001  
TITLE: ORCHESTRA comparison tasks frequently lack positive exact-TID ownership evidence  
SEVERITY: HIGH  
TEST ID: COMP-001, COMP-002, COMP-003  
STATUS: INCONCLUSIVE_OWNERSHIP_NOT_PROVEN

OBSERVATION: The matched CFS matrix completed all 9 rows. The ORCHESTRA matrix completed 9 rows, but only 2 rows passed the all-target ownership gate; 7 rows had at least one missing or non-positive exact task status.

EXPECTED: Every timed ORCHESTRA row must show positive accepted and dispatched evidence for every target PID before its elapsed time can be interpreted as an ORCHESTRA result.

EVIDENCE: `comparison/orchestra_matrix.csv`; `comparison/OWNERSHIP_GATE.md`; `workload/ownership_status_after_1s.stdout`; `workload/ownership_map_after_2s.stdout`.

REPRODUCIBILITY: 7/9 failures in one 3×(1,2,4 worker) matrix. The separate positive ownership run produced accepted=16, dispatched=16, running=16, effective=16 at one second and accepted=40/dispatched=40/running=39/effective=39 at two seconds.

FIRST FAILURE POINT: The exact-TID ownership observation during the comparison launch protocol, before performance interpretation.

LIKELY COMPONENT: sched_ext ownership/admission lifecycle, bridge publication timing, or workload launch protocol.

MOST LIKELY CAUSE: The comparison protocol can observe a task before a stable exact per-task record exists, and the full-switch path can leave target tasks without timely positive telemetry. The evidence does not distinguish a kernel lifecycle race from a harness timing issue.

ALTERNATIVE CAUSES: CPU affinity interaction, background scheduling interference, or workload completion before the status snapshot.

EVIDENCE AGAINST ALTERNATIVES: A separate exact-TID run succeeded; the failures recur across worker counts and include missing status lines. No ORCHESTRA kernel error accompanied them.

CONFIDENCE: HIGH for the observation; LOW for the root cause.

IMPACT: Correctness of ownership claims, performance claim scope, reproducibility.

RECOMMENDATION: Establish positive per-task admission/enqueue/running evidence before timing and correlate it with task lifecycle counters. Do not use the failed rows for scheduler performance conclusions.

IMPLEMENTATION MODIFIED: NO.

## F-002 — apparent severe slowdown is not a valid ORCHESTRA performance claim

FINDING ID: F-002  
TITLE: Ownership-invalid ORCHESTRA rows are much slower than the CFS baseline  
SEVERITY: HIGH  
TEST ID: COMP-001, COMP-002, COMP-003  
STATUS: INCONCLUSIVE_OWNERSHIP_NOT_PROVEN

OBSERVATION: CFS means were 308.0 ms (1 worker), 305.67 ms (2), and 307.33 ms (4). ORCHESTRA raw means were 4,715.33 ms, 7,869.67 ms, and 11,839.0 ms respectively, with high variance and failed ownership gates in 7/9 rows.

EXPECTED: Comparable timing requires identical workload/affinity/protocol plus proven ORCHESTRA ownership for every timed task.

EVIDENCE: `baseline/cfs_matrix.csv`; `comparison/orchestra_matrix.csv`; `comparison/OWNERSHIP_GATE.md`.

REPRODUCIBILITY: Three repetitions for each worker count. The raw timing inflation recurs, but ownership is not proven for most rows.

FIRST FAILURE POINT: Ownership validation, not the elapsed-time calculation.

LIKELY COMPONENT: Linux interaction / sched_ext ownership / bridge protocol / workload harness.

MOST LIKELY CAUSE: Unknown. The data shows a severe forward-progress or measurement-protocol problem, not a confirmed scheduler overhead value.

ALTERNATIVE CAUSES: Tasks may have run partly through the normal scheduler, status snapshots may have missed short-lived records, or the scheduler path may have delayed some tasks.

EVIDENCE AGAINST ALTERNATIVES: The positive controlled ownership run and action runs demonstrate that the same bridge and scheduler can produce exact positive telemetry for individual tasks.

CONFIDENCE: HIGH that the comparison is unusable for a broad performance claim; LOW for mechanism.

IMPACT: Performance, reproducibility, research conclusion scope.

RECOMMENDATION: Fix the existing ownership-validation protocol or add an approved observable lifecycle gate before collecting a valid comparison matrix. No performance win/loss should be claimed from these rows.

IMPLEMENTATION MODIFIED: NO.

## F-003 — SLEEP is only partially validated

FINDING ID: F-003  
TITLE: Future SLEEP deadline and release were observed, but one-shot expiry is not a complete lifecycle
SEVERITY: MEDIUM  
TEST ID: 02-050 / ACT-005  
STATUS: INCONCLUSIVE

OBSERVATION: Before the future deadline, the task had accepted=1, dispatched=0, running=0, effective=0. After the deadline, dispatch and effective counters increased and deferred release increased. Later repeated enqueue attempts using the expired one-shot directive produced fallback counts.

EXPECTED: SLEEP should suppress execution until its deadline and provide a defined, repeatable wake/release lifecycle.

EVIDENCE: `actions/SLEEP_TIMELINE_t0_status.stdout`; `actions/SLEEP_TIMELINE_t05_status.stdout`; `actions/SLEEP_TIMELINE_t15_status.stdout`; `actions/SLEEP_TIMELINE_t25_status.stdout`; `actions/SLEEP_TIMELINE_telemetry_post.stdout`.

REPRODUCIBILITY: One controlled timeline plus the earlier SLEEP run. The no-early/deadline-release behavior is observed; repeated post-expiry behavior remains limited to the one-shot protocol.

FIRST FAILURE POINT: No-early behavior did not fail; the unresolved point is directive lifecycle after expiry.

LIKELY COMPONENT: action implementation / directive lifecycle.

MOST LIKELY CAUSE: The existing SLEEP directive is one-shot and rejects an expired `not_before` value on later enqueue attempts.

ALTERNATIVE CAUSES: Test harness reuse of an intentionally expired directive or insufficient task-state reset.

EVIDENCE AGAINST ALTERNATIVES: The kernel telemetry explicitly records deferred and release behavior, while fallback reason is associated with the expired parameters.

CONFIDENCE: HIGH for observed behavior; MEDIUM for lifecycle interpretation.

IMPACT: Correctness and observability of repeated sleep/wake use.

RECOMMENDATION: Define and expose directive clear/refresh semantics, then repeat a multi-cycle sleep/wake test.

IMPLEMENTATION MODIFIED: NO.

## F-004 — full stress script blocked by a host-specific safety hazard

FINDING ID: F-004  
TITLE: Existing stress script requests unsafe memory pressure on this host
SEVERITY: MEDIUM  
TEST ID: STRESS-001  
STATUS: BLOCKED_FOR_SAFETY

OBSERVATION: The script derives `STRESS_MB` as half of the 15 GiB host RAM and starts two `stress --vm` workers with that per-worker size.

EXPECTED: Stress tests must remain within a disposable host's thermal, memory, and storage safety envelope.

EVIDENCE: `benchmarks/real-machine/stress_suite.sh`; `stress/STATUS.md`; `environment/repo_state_final.stdout`.

REPRODUCIBILITY: Deterministic from script arithmetic while `/usr/bin/stress` is installed: approximately 15.4 GiB requested by two workers.

FIRST FAILURE POINT: Safety gate before execution.

LIKELY COMPONENT: workload script assumption / environment.

MOST LIKELY CAUSE: The script assumes the host can tolerate two workers each receiving half of physical RAM and provides no safe memory-size parameter.

ALTERNATIVE CAUSES: None needed for the block; the command was intentionally not started.

EVIDENCE AGAINST ALTERNATIVES: `/tmp` and root storage were healthy, but that does not make the fixed memory request safe.

CONFIDENCE: HIGH.

IMPACT: Stress coverage; no runtime result is claimed.

RECOMMENDATION: Provide an approved, bounded stress configuration and ownership-validating ORCHESTRA mode before running this suite.

IMPLEMENTATION MODIFIED: NO.

## F-005 — comparison tooling is not portable or complete on this host

FINDING ID: F-005  
TITLE: Existing benchmark scripts cannot be run safely as written
SEVERITY: MEDIUM  
TEST ID: PERF-001, PERF-002, STRESS-002  
STATUS: BLOCKED

OBSERVATION: `benchmark_suite.sh` and `full_compare.sh` contain `/home/vagrant` assumptions and broad BPF cleanup paths. `scx_simple` and `perf` are absent. The stress script's ORCHESTRA mode checks sched_ext state but does not opt target tasks into ORCHESTRA.

EXPECTED: Comparison tooling must be location-independent, preserve unrelated BPF state, and prove scheduler ownership.

EVIDENCE: inspected repository scripts; `environment/repo_state_final.stdout`; `stress/STATUS.md`; `comparison/OWNERSHIP_GATE.md`.

REPRODUCIBILITY: Script contents and missing command paths are deterministic on this host.

FIRST FAILURE POINT: Safety/tooling prerequisite gate.

LIKELY COMPONENT: benchmark infrastructure.

MOST LIKELY CAUSE: The scripts were authored for a different filesystem layout and do not implement the campaign ownership protocol.

ALTERNATIVE CAUSES: None required for the blocked classification.

EVIDENCE AGAINST ALTERNATIVES: Manual safe commands produced build, lifecycle, action, baseline, and ownership evidence without broad cleanup.

CONFIDENCE: HIGH.

IMPACT: Coverage and reproducibility, not scheduler correctness by itself.

RECOMMENDATION: Supply a separately approved portable benchmark harness and install optional tools only with user authorization.

IMPLEMENTATION MODIFIED: NO.

## F-006 — research architecture layers are absent from the kernel prototype

FINDING ID: F-006  
TITLE: Kernel signal/predictor/Q/controller/RT/NUMA/distributed claims are outside this revision
SEVERITY: MEDIUM  
TEST ID: ARCH-001 and blocked checklist items
STATUS: BLOCKED_NOT_IMPLEMENTED

OBSERVATION: Source inspection found the stage7 sched_ext scheduler, bridge ABI, action maps, task state, and telemetry. It did not find executable kernel implementations of the authenticated predictive signal bus, predictor, kernel S1/S2/S3/S4/Q, feedback controller, full Hybrid Safety Layer, NUMA policy, or distributed tier.

EXPECTED: A real-machine claim requires an implemented and observable feature.

EVIDENCE: `IMPLEMENTATION_MATRIX.md`; `kernel/sched_ext/orchestra_scx_stage7.bpf.c`; `kernel/sched_ext/bridge/orchestra_bridge.c`; userspace `make test` output is explicitly not promoted to kernel validation.

REPRODUCIBILITY: Source audit and current checklist audit.

FIRST FAILURE POINT: Implementation-maturity audit before runtime testing.

LIKELY COMPONENT: implementation scope.

MOST LIKELY CAUSE: The repository contains a stage7 kernel prototype while the broader architecture remains userspace/simulation work.

ALTERNATIVE CAUSES: None needed to classify absent executable features.

EVIDENCE AGAINST ALTERNATIVES: Userspace tests passed, but no kernel map/output/telemetry exposes the required architecture layers.

CONFIDENCE: HIGH.

IMPACT: Claim scope and acceptance readiness.

RECOMMENDATION: Implement and instrument each missing layer in a future development phase, then rerun the applicable checklist. This campaign did not modify implementation code.

IMPLEMENTATION MODIFIED: NO.

## F-007 — initial campaign harness failures were preserved

FINDING ID: F-007  
TITLE: First BPF compile and action harness attempts failed due command/harness mistakes
SEVERITY: LOW  
TEST ID: BPF-001 and action harness setup
STATUS: FAIL (harness only)

OBSERVATION: The first BPF compile expanded a shell variable before execution and omitted the kernel include path. The first combined action harness referenced a missing output directory/literal variable paths. Both failures were preserved; corrected retries passed and no source was changed.

EXPECTED: Evidence harnesses should invoke the documented existing commands with correct paths.

EVIDENCE: `COMMANDS.log`; `build/bpf_compile.stderr`; `actions/HARNESS_FAILURE.md`; `build/bpf_compile_retry.stdout`; individual action evidence.

REPRODUCIBILITY: Each failure occurred once in the initial attempt; corrected commands then completed.

FIRST FAILURE POINT: External command orchestration.

LIKELY COMPONENT: test harness / shell expansion.

MOST LIKELY CAUSE: Incorrect quoting and missing campaign directory creation.

ALTERNATIVE CAUSES: None relevant to the source implementation.

EVIDENCE AGAINST ALTERNATIVES: The same existing source compiled and loaded after correcting only invocation paths.

CONFIDENCE: HIGH.

IMPACT: Evidence quality; no implementation impact.

RECOMMENDATION: Keep command wrappers path-safe and preserve first failures in future campaigns.

IMPLEMENTATION MODIFIED: NO.
