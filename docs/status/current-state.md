# ORCHESTRA-OS verified current state

- Audit date: 2026-08-14
- Repository commit: `853cfb40e23137e721557fe75f7475a3d4edc970`
- Branch: `main` (`origin/main` at the same commit)
- Current milestone: Stage 7 sched_ext bridge prototype with the P0 partial-switch ownership fix and bounded VirtualBox runtime gate passed; no bare-metal sched_ext acceptance has been run
- Active work-package boundary: WP1 kernel foundation, with userspace precursors for WP2-WP6
- Overall claim class: mixed; see the component boundaries below

This file is a handoff index. The paper, ADRs, experiment contracts, raw
artifacts, and test protocols remain authoritative for their respective
decisions and evidence.

## Claim boundary

The repository is not deployment-ready and does not contain a complete
ORCHESTRA kernel scheduler. It contains:

- a pre-kernel discrete-event simulation reported by the research paper;
- a real-process userspace prototype in which Linux CFS/EEVDF still performs
  final dispatch;
- a partial-opt-in sched_ext BPF prototype and a privileged userspace map
  bridge;
- VirtualBox evidence for exact Linux 6.12.96 boot, BPF verification, attach,
  bounded stability, action paths, deferred SLEEP/THROTTLE release, legal
  MIGRATE placement, clean unload, and explicit SCHED_EXT task ownership;
- no bare-metal sched_ext execution evidence;
- no kernel implementation of authenticated signal frames, prediction,
  adaptive learning, S1-S4/Q, or the slower feedback controller.

Repository "Stage" numbers are historical development milestones. They are
not equivalent to the WP1-WP10 exit gates.

## Verified working components

### Userspace

- Canonical actions: RUN, SLEEP, MIGRATE, THROTTLE, YIELD.
- Canonical 128-byte, fixed-endian signal payload plus HMAC-SHA256 tag.
- Generation-stamped two-slot shared-memory publication with bounded readers.
- Field, identity, sequence, freshness, epoch, and constant-time tag checks.
- Observed-state fallback when a prediction lacks confidence.
- Fixed-gain predictor and robust observation-noise estimate.
- Tabular per-process learning, directive-aligned state thresholds, epsilon
  annealing, local/difference reward blending, and bounded consensus.
- S1-S4 and `Q = (S1*S2*S3*S4)^(1/4)`.
- Experimental burst-sensitive S4 diagnostics kept outside historical Q.
- Bounded, slower-timescale multi-actuator controller state machine.
- Process cleanup, signal teardown, strict CSV validation, and reproducible
  userspace benchmark/microbenchmark tooling through the committed v5
  experiment contracts.

On 2026-08-14, `make test` passed:

- 25/25 named unit tests under GCC ASan/UBSan;
- the same 25/25 tests under the legacy transport and Clang passes;
- generation-stamped thread and MAP_SHARED process stress tests;
- 21 benchmark-runner validator tests;
- 4 signal-publication runner tests;
- 34 strict CSV validator tests;
- five bounded integration scenarios (baseline, ORCHESTRA, tamper,
  controller-tamper, and signal-stop).

### Kernel prototype

The current kernel path is `orchestra_scx_stage7.bpf.c`, not the Stage 6
loader skeleton. It uses exact-schema control, directive, identity, task,
telemetry, per-task telemetry, and deferred-timer maps. It is partial-switch
only: a task must explicitly enter SCHED_EXT.

The final VirtualBox runtime gate on 2026-08-14 established:

- a non-opted task did not increment enqueue/running ownership counters;
- an opted task incremented enable, enqueue, RUN, and running counters;
- MIGRATE requests reached the targeted `SCX_DSQ_LOCAL_ON` path and 10/10
  observed runs reached CPU 3;
- SLEEP and THROTTLE deferred and later released through the pinned timer map;
- concurrent per-task actions did not cross-mix identities;
- the scheduler detached cleanly through three lifecycle cycles plus a
  pre-pinned bridge-contract cycle;
- 24/24 bounded fallback tasks completed; this is a correctness gate, not a
  performance claim.

## Unverified or incomplete components

- The validated VM uses Linux 6.12.96. Newer or older kernels may require a
  sched_ext API compatibility build and separate verifier validation.
- The bridge development headers and link inputs are not installed on the
  current host (`libbpf-dev` and `libelf-dev` are absent).
- No bare-metal BPF verifier, attach, ownership, action, watchdog, or detach
  test has run.
- YIELD remains a bounded relinquish approximation; physical fairness and
  latency validation remain pending.
- THROTTLE and SLEEP use bounded deferred eligibility; physical timing and
  bandwidth validation remain pending.
- MIGRATE placement was observed in the VM; hotplug and physical-contention
  behavior remain unvalidated.
- Unknown actions use RUN fallback, but an invalid action cannot be published
  through the current CLI and lacks a current owned-task runtime test.
- The bridge map ABI is local native-endian packed data and is not the
  authenticated canonical signal-frame protocol.
- Deterministic PID-reuse, map-capacity-exhaustion, and CPU-hotplug race
  campaigns remain pending despite the corrected lifetime identity path.
- The loader and bridge now validate exact map schemas, identity, generation,
  expiry, and timer-map pinning before attach; deterministic stress campaigns
  remain pending.
- The current userspace binary emits 120-column metrics v6, but there is no
  committed v6 JSON schema or v6 experiment manifest and the benchmark runner
  supports only v2-v5. The latest VBox paper-CPU harness therefore ran but was
  excluded for schema mismatch.
- No kernel tests cover real-time/deadline non-interference, starvation,
  affinity/cpuset constraints, CPU hotplug, NUMA, cgroups, or security faults.
- Earlier Stage 8/9 benchmark interpretations that predate the P0 ownership fix
  do not prove ORCHESTRA-owned scheduling and must not be used as performance
  evidence.

## Current machine

Readiness classification: **VM gate passed; controlled physical pilot only**.

| Item | Verified value |
| --- | --- |
| OS | Kali GNU/Linux Rolling 2026.3 (Debian family) |
| Kernel | `7.0.12+kali-amd64` |
| Architecture | x86_64 |
| Virtualization | none detected (bare metal) |
| CPU | Intel Core i5-10310U, 1 socket, 4 cores, SMT2, 8 logical CPUs |
| NUMA | one node, CPUs 0-7 |
| sched_ext sysfs | present; state `disabled`; enable sequence 0 at audit |
| BTF | `/sys/kernel/btf/vmlinux`, present |
| Required config | BPF, BPF_SYSCALL, BPF_JIT, DEBUG_INFO_BTF, BPF_EVENTS, and SCHED_CLASS_EXT all `y` |
| clang | 21.1.8 |
| bpftool/libbpf runtime | bpftool 7.7.0; libbpf 1.7 |
| Rust | rustc/cargo 1.95.0; not required by the current C prototype |
| Missing build inputs | `libbpf-dev`, `libelf-dev`, exact 7.0.12 sched_ext tool headers/source |

No kernel replacement or reboot is indicated. Root is required for BPF load,
map pinning, task opt-in, and detach. Unprivileged BPF is disabled.

## Next acceptance gate

The next milestone is **bare-metal Linux 7.0.12 build/verifier compatibility
and a non-destructive partial-switch acceptance run**. It is not another
simulator feature and not the SuperTuxKart demonstration.

The gate passes only when a source-hashed build can:

1. compile against the exact running-kernel API;
2. pass the BPF verifier and attach as the identified ORCHESTRA scheduler;
3. prove a non-opted task remains outside ORCHESTRA;
4. prove an opted bounded task reaches enable/enqueue/running callbacks;
5. exercise owned-task RUN and YIELD;
6. exercise an invalid/unknown directive through a controlled test path and
   observe RUN fallback;
7. inspect requested versus effective telemetry without conflating them;
8. detach only the link and pins created by the test;
9. verify sched_ext state returns to `disabled` and the task returns to the
   normal Linux scheduler;
10. exercise verifier/load failure and watchdog/exit recovery safely; and
11. retain the environment, commands, stdout/stderr, dmesg excerpt, map data,
    scheduler state transitions, hashes, anomalies, and pass/block result.

Use `Orchestra updated check list .docx` as the broad real-machine protocol.
It is the newer, 36-phase expansion of the earlier checklist; do not create a
duplicate checklist.

## Continuation order

1. Obtain the exact Kali `7.0.12-2kali1` source/tool headers and install the
   userspace development dependencies, after host-change approval.
2. Add a repository-local, out-of-tree build recipe that never writes generated
   headers or objects over source files.
3. Port the Stage 7 insertion calls to the Linux 7.0 sched_ext API while
   preserving action/fallback semantics; document the compatibility decision
   if it changes a contract.
4. Add source-level tests for bridge CLI parsing, map schema/ownership checks,
   generation/cache invalidation, action bounds, and opt-in ABI portability.
5. Replace broad cleanup and global struct_ops-link detachment in the current
   scripts with exact link/map ownership tracking and a recovery trap.
6. Build and run verifier-only loading with complete logs; do not opt in a task
   until the verifier and attach/detach path is clean.
7. Run the negative non-opt-in ownership test, then a single short opted RUN
   test, then YIELD and controlled invalid-action fallback.
8. Run clean detach, scheduler-exit, and bounded watchdog/failure recovery;
   verify state and conventional scheduling after every case.
9. Capture a new immutable bare-metal artifact set and update the relevant ADR,
   kernel result, and this status index.
10. Only after correctness/safety acceptance, validate effective MIGRATE and
    define real SLEEP/THROTTLE contracts before any comparative workload demo.

## Commands for the next controlled session

Read-only recheck:

```bash
git status --short --branch
uname -r
cat /sys/kernel/sched_ext/state
bash kernel/sched_ext/scripts/check_kernel_config.sh
bpftool version
clang --version | head -n 1
```

Proposed dependency installation, not executed during this audit:

```bash
sudo apt update
sudo apt install --no-install-recommends \
  libbpf-dev libelf-dev zlib1g-dev linux-source-7.0
```

Before using those packages, verify that `linux-source-7.0` resolves to the
same `7.0.12-2kali1` source version as the running kernel package. Installing
these development packages does not replace the running kernel, but it changes
host package state and therefore requires approval.

Do not run the current `p0_ownership_retest.sh`, `stage8_validate.sh`, or old
reproduction script unmodified on this host. They contain VirtualBox-specific
paths and/or broad `/sys/fs/bpf` cleanup and global struct_ops detach logic that
can disturb unrelated BPF programs or schedulers.
