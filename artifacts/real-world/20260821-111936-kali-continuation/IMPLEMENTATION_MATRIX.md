# Implementation maturity matrix

Scope is commit `82f69cbac2d9bf4ffa1372550f73d9c2c084b8f9` plus the pre-existing working-tree state. Statuses distinguish the kernel prototype from userspace tests and research specification.

| Component | Status | Evidence | Testable on this machine? |
|---|---|---|---|
| sched_ext scheduler | KERNEL_PROTOTYPED | Fresh stage7 BPF object loaded and unloaded; `sched_ext/state`; `sched_ext` kernel log | Yes; lifecycle and selected task paths |
| bridge | KERNEL_PROTOTYPED | Existing `orchestra_bridge` status, identity, directive and validation commands; fresh `-Werror` build | Yes |
| RUN | KERNEL_PROTOTYPED | Exact per-task accepted/dispatched/running/effective telemetry | Yes; observed in controlled trials |
| YIELD | KERNEL_PROTOTYPED | Exact per-task YIELD telemetry and global `yield_disp` counter | Yes; observed in controlled trial |
| MIGRATE | KERNEL_PROTOTYPED | Requested CPU 1, dispatched CPU 1, actual CPU 1, target counter | Yes on this single-socket host |
| THROTTLE | KERNEL_PROTOTYPED | Valid 20 ms budget produced deferred/throttled state and release telemetry | Yes; only under forced low budget |
| SLEEP | KERNEL_PROTOTYPED | Future deadline suppressed dispatch; release observed; one-shot expiry generated later bad-parameter fallbacks | Partially; broader lifecycle remains inconclusive |
| Signal Bus | NOT_IMPLEMENTED for kernel runtime | Existing kernel maps contain directives/telemetry, but no executable authenticated predictive frame bus | No kernel-level validation |
| integrity/freshness | USERSPACE_VALIDATED / KERNEL_PROTOTYPED checks | Bridge identity, generation, lease, PID/CPU validation; userspace HMAC tests passed | Input/generation checks only; no kernel cryptographic claim |
| predictor | USERSPACE_VALIDATED only | Userspace unit/integration tests; no kernel predictor output exposed | No kernel validation |
| S1/S2/S3/S4/Q | USERSPACE_VALIDATED only | Userspace metric tests; required kernel inputs are not exposed | No kernel validation |
| controller | USERSPACE_VALIDATED only | Userspace controller tests; no kernel controller telemetry | No kernel validation |
| RT bypass / Hybrid Safety Layer | NOT_IMPLEMENTED | No executable kernel RT bypass/coexistence implementation in this revision | No |
| NUMA-aware scheduling | NOT_IMPLEMENTED / N/A environment | Host has one NUMA node; no kernel NUMA policy identified | Cross-node test impossible |
| distributed tier | NOT_IMPLEMENTED | No distributed implementation or valid peer/test infrastructure | No |

The compiled object and successful load prove a kernel prototype exists; they do not promote the unimplemented architecture layers to experimental validation or deployment readiness.
