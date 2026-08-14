# ORCHESTRA-OS VirtualBox runtime validation — 2026-08-14

## Verdict

The remediated sched_ext prototype passes the bounded VirtualBox runtime gate
on `orchestra-scx-lab` (Fedora, Linux 6.12.96, four vCPUs). This is VM evidence,
not physical-machine readiness or a performance result.

The VM ended with sched_ext `disabled`, no struct_ops links, and no
`/sys/fs/bpf/orchestra` pins.

## Runtime defects discovered and fixed

1. `dispatch()` called `scx_bpf_consume(SCX_DSQ_GLOBAL)`. The verifier accepted
   it, but sched_ext immediately detached with `invalid DSQ ID
   0x8000000000000001`. The reserved global DSQ is now left to the scheduler
   core.
2. The deferred timer map lost its userspace reference when `bpftool` exited.
   SLEEP remained stranded until the 30-second sched_ext watchdog detached the
   scheduler (`failed to run for 34.785s`). A dedicated loader now pins every
   exact-schema runtime map before struct_ops attach initializes the timer.
   Late bridge pinning is rejected.
3. The timer map's original 16-character name exceeded the 15-character BPF
   object-name limit. Its canonical name is now `orch_defer_tmr`.
4. MIGRATE used the requested CPU only from `select_cpu()`; ordinary re-enqueue
   went to the global DSQ. Legal targets now use `SCX_DSQ_LOCAL_ON | target_cpu`
   after online/affinity validation.

## Final-object evidence

- Verifier load and struct_ops attach: passed.
- Persistent timer after loader exit: observed increasing timer-tick telemetry.
- RUN: actual execution observed by `running()`, no fallback or errors.
- YIELD with a RUN peer: both tasks progressed; YIELD recorded effective runs.
- SLEEP: zero runs before eligibility, then release to the selected legal CPU.
- THROTTLE: runtime-budget exhaustion caused defer/release events without errors.
- MIGRATE: requested CPU 3, dispatched CPU 3, actual CPU 3; 10/10 target runs,
  zero off-target runs and zero task errors.
- Illegal MIGRATE: a CPU-0-only task rejected target CPU 3 with bridge exit 7.
- Concurrent per-task directives: four identities simultaneously held RUN,
  YIELD, SLEEP, and THROTTLE directives without cross-task mixing.
- Full-switch fallback progress: 24/24 bounded CPU-work tasks completed.
- Expired directive and stale publisher lease: both fell back safely; telemetry
  recorded one expiry and eight stale-lease observations.
- Exact thread identity: a non-leader TID was admitted as TGID:TID:start-time.
- RT bypass: a SCHED_FIFO priority-1 task had no ORCHESTRA identity record.
- Lifecycle: three final attach/detach cycles completed, followed by a separate
  pre-pinned bridge-contract cycle; every cycle returned to `disabled`.

## Safe test evidence

- GCC ASan/UBSan and Clang unit suites: passed.
- 30/30 named algorithm/C unit tests: passed in each compiler pass.
- Publication stress: 2,000 generations, four readers, no torn accepted frame,
  regression, duplicate acceptance, crash, or hang.
- Bridge ABI/parser and sched_ext source invariants: passed.
- Strict bridge/loader builds in the guest: passed.
- Canonical and compatibility BPF compile-only builds: passed.
- Repository `make check` and `git diff --check`: passed.

## Still pending

- Physical-machine execution.
- CPU-hotplug/cpuset race injection.
- Deterministic PID-reuse and map-capacity exhaustion tests.
- Long-duration soak, deliberate final-object watchdog fault injection, and
  crash/restart recovery campaigns.
- Quantitative latency, fairness, timer overhead, bandwidth, and performance
  evaluation.
- New-kernel sched_ext API port validation.

No VM performance benchmark, physical-machine test, kernel replacement, or
host-kernel operation was performed.
