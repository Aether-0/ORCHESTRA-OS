# Implementation and target-test maturity matrix

Evidence basis: repository revision
68295dc134774c7699764b3234e40ac7c764cc5c, README.md,
docs/status/current-state.md, current sched_ext sources, and prior
physical-Kali campaign artifacts.

| Component | Current class | Target readiness | Evidence / boundary |
|---|---|---|---|
| Stage-7 sched_ext scheduler | KERNEL_PROTOTYPED | Ready for exact 7.0.12 preflight | orchestra_scx_stage7.bpf.c; prior 7.0 attach/unload evidence |
| Bridge CLI and ABI maps | KERNEL_PROTOTYPED | Ready to build/hash | orchestra_bridge.c, orchestra_bridge_v1.h, exact-schema checks |
| Map-pinning loader | KERNEL_PROTOTYPED | Required for target load | orchestra_loader.c; pins timer map before attach |
| RUN | KERNEL_PROTOTYPED | Per-task proof pending | Prior global/full-switch activity is not isolated action proof |
| YIELD | KERNEL_PROTOTYPED | Per-task proof pending | Requested/dispatched counters must be tied to the target TID |
| MIGRATE | KERNEL_PROTOTYPED | Repeatable CPU proof pending | Prior physical attempt used an invalid restricted-affinity protocol |
| SLEEP | KERNEL_PROTOTYPED | Deferred timing proof pending | sleep accepted, deferred, release, and no-early-run evidence required |
| THROTTLE | KERNEL_PROTOTYPED | Duty-cycle proof pending | Acceptance or slice shortening is insufficient |
| Negative/positive ownership | KERNEL_PROTOTYPED | Mandatory next gate | Non-opted exclusion plus exact live-TID enable/enqueue/running |
| Userspace signal frame/HMAC | USERSPACE_VALIDATED | Kernel validation blocked | Current BPF bridge ABI is not the full authenticated userspace signal protocol |
| Predictor | USERSPACE_VALIDATED | Kernel validation blocked | No real-machine BPF predictor output exposed |
| S1/S2/S3/S4/Q | USERSPACE_VALIDATED | Kernel validation blocked | Do not copy userspace or simulation Q into kernel results |
| Feedback controller | USERSPACE_VALIDATED | Kernel validation blocked | No kernel controller telemetry/actuator loop established |
| Hybrid Safety Layer | SPECIFIED / partial prototype | Target test limited | FIFO/RR coexistence is not proof of the full safety layer |
| Instrumentation | KERNEL_PROTOTYPED | Target telemetry gate pending | Requested/effective/per-task fields exist; causal attribution must be shown |
| NUMA-aware scheduling | SPECIFIED / unvalidated | Depends on target topology | A single-node target cannot validate multi-node behavior |
| Distributed/cluster tier | SPECIFIED | Not testable in this campaign | Single-host Kali is not distributed validation |
| Deployment readiness | NOT IMPLEMENTED as a claim | Not ready | Prior and current evidence prohibit deployment claims |
