# Full-objective requirement gap map

This map reconciles the user objective with the authoritative release-readiness ledger, the 519-item machine checklist, and the current kernel tree. It is an audit artifact, not an implementation. No protected source, test, or script was edited.

## Completion rule

The objective requires every applicable item to be implemented, integrated, observed on the real machine, and supported by reproducible evidence. A userspace precursor, compiled BPF object, successful scheduler attach, or one positive action run cannot close a broader kernel requirement.

## Work-package audit

| Work package | Required end state | Current evidence | Status | Blocking evidence |
|---|---|---|---|---|
| WP1 Linux kernel integration | Approved kernel insertion/precedence, task/run-queue interfaces, build/boot/recovery automation, conventional/deadline/RT fallback regression, kernel smoke | Stage7 sched_ext object loads on the running kernel; selected actions and unload work; no boot/recovery campaign | INCOMPLETE | `docs/operations/release-readiness-plan.md` WP1 ledger; `REAL_WORLD_TEST_REPORT.md` §§8–9, 12 |
| WP2 Signal Bus | Kernel-safe fixed-point authenticated frame with prediction horizon, hierarchy, lifetime/concurrency proof, key lifecycle, duplicate/replay rejection, fuzzing, recovery, verification budget | Userspace MAP_SHARED/HMAC precursor and bridge directive maps; no kernel predictive frame or safe kernel tamper injector | BLOCKED_NOT_IMPLEMENTED | `IMPLEMENTATION_MATRIX.md`; `make_test_continuation.stdout`; release ledger WP2 |
| WP3 Predictive Engine | Held-out calibration, versioned artifacts, no-look-ahead proof, recalibration/degraded cases, kernel-path latency/resource budget | Userspace predictor tests only; no kernel predictor outputs | BLOCKED_NOT_IMPLEMENTED | release ledger WP3; report §14 |
| WP4 Adaptive Scheduling | Kernel contracts for all five actions, admission/removal, safety precedence, dispatch outcomes, fairness/starvation controls, fallback, bounded exploration, stress evidence | Stage7 maps and action paths; controlled RUN/YIELD/MIGRATE/THROTTLE/SLEEP evidence; no full adaptive policy, safety-class, or stress gate | INCOMPLETE | `kernel/sched_ext/orchestra_scx_stage7.bpf.c`; report §§10–12, 24 |
| WP5 Measurement and Control | Kernel/per-level S1–S4/Q, versioned compliance, stability/saturation, controller rollback/re-entry, causal actuator effects, false-good tests | Userspace S1–S4/Q/controller tests; no kernel metric/controller stream | BLOCKED_NOT_IMPLEMENTED | release ledger WP5; report §§15–16, 22 |
| WP6 Instrumentation | Kernel tracepoints/events for dispatch/actions/fallback/controller with coherent timestamps, schema metadata, drop accounting, overhead | Per-task/global BPF maps and counters only; insufficient causal trace coverage | BLOCKED_INSUFFICIENT_OBSERVABILITY | release ledger WP6; checklist Phase 10 |
| WP7 Experimental Evaluation | Isolated/pinned/counterbalanced protocol, identical replay, predeclared outcomes/power rationale, latency/fairness/energy/throughput/overhead/robustness, valid Linux baseline | CFS n=3 matrix and ownership-invalid ORCHESTRA matrix; no valid broad scheduler comparison | INCONCLUSIVE_OWNERSHIP_NOT_PROVEN | `comparison/orchestra_matrix.csv`; report §§17–19, 30 |
| WP8 Scale and multi-level coordination | Core/socket/NUMA/node/cluster responsibilities, ordering/clock/consistency, local continuity, scale/remote-memory costs, limits | One NUMA node, one host, no distributed implementation/peer; 1/2/4 matrix ownership inconsistent | BLOCKED_NOT_IMPLEMENTED / BLOCKED_BY_ENVIRONMENT | report §§27–28; release ledger WP8 |
| WP9 Security/reliability/resilience | Threat/trust model, production key lifecycle, spoof/replay/corruption/auth campaigns, combined faults, recovery distributions, soak, monitoring, risk decisions | Userspace HMAC/tamper/validation and scheduler unload; no kernel key lifecycle, full fault campaign, or long soak | INCOMPLETE | report §§25–29; release ledger WP9 |
| WP10 Optimization/deployment readiness | Profile-led safe optimization, stable defaults, sustained acceptance, rollback/operator docs, end-to-end regression, formal readiness review | No qualifying integrated evidence; upstream WP1–WP9 gates remain open | BLOCKED_BY_UPSTREAM_GATES | release ledger WP10; `CAMPAIGN_STATUS.md` |

## Canonical action audit

| Action | Current implementation | Evidence | Remaining requirement |
|---|---|---|---|
| RUN | Stage7 directive/DSQ path | Exact task counters positive in controlled run | Matrix across lifecycle/controller/safety states and valid comparative trials |
| YIELD | Stage7 global queue-tail/minimum-slice path | Exact task counters and yield dispatch counter | Same full matrix, fairness and responsiveness evidence |
| MIGRATE | Stage7 CPU validation and LOCAL_ON/target dispatch | Actual CPU and target counters observed | Repeated/multi-task/load/affinity/NUMA consequence matrix |
| THROTTLE | Stage7 budget/period/deferred path | Forced 20 ms budget produced deferred/throttled state | Sustained workload matrix, fairness, saturation, recovery, causal metrics |
| SLEEP | Stage7 future deadline/deferred DSQ path | No early dispatch and post-deadline release observed | Defined one-shot refresh/clear lifecycle and repeated wake tests |

## Architecture requirements not represented by current kernel maps

- Authenticated predictive frame with key provisioning/rotation/revocation/recovery.
- Prediction horizon/confidence output in the kernel scheduling path.
- Per-level/core/socket/NUMA/node/cluster hierarchy and consistency behavior.
- Kernel state construction from CPU, memory, thermal, queue, and predicted state.
- Kernel adaptive policy/reward/exploration/consensus and controller causal credit.
- Hybrid Safety Layer with RT/exempt precedence and safe fallback.
- Kernel S1, S2, S3, S4, Q plus thundering-herd temporal stability.
- Selective kernel tracepoints and reason-specific event accounting.
- Cross-node NUMA and distributed tier behavior.
- Long-duration leak/instability evidence and production security/key lifecycle.

## Gate conclusion

The current source can be promoted only within the demonstrated stage7 prototype scope. The user objective remains open. Completing it requires implementation authority beyond the current `AGENTS.md` test-only rules, implementation work in the kernel/BPF/bridge and likely existing test infrastructure, suitable multi-NUMA/distributed test environments, and a new validation campaign after those changes.
