# ORCHESTRA-OS Real-Machine Validation Report

Campaign: real-machine-20260821-094227-kali-2qqYxp  
Completed: 2026-08-21T10:02:49+01:00  
Repository: /home/sharda/Downloads/ORCHESTRA-OS-main  
Commit: 07c787c4eeac01a2f9d60916577806d00863b15f  
Branch: main  
Host: kali  
Kernel: 7.0.12+kali-amd64

## Executive Summary

The running kernel passed the sched_ext, BTF, and eBPF capability gates. The userspace regression suite and a fresh out-of-tree build of the stage7 BPF scheduler, bridge, map-pinning loader, and fixed workload passed. The loader attached the scheduler three times and unloaded it three times without touching unrelated BPF state. Final sched_ext state is disabled.

The stage7 scheduler produced real per-task evidence for RUN, YIELD, and MIGRATE, and exposed deferred SLEEP and budgeted THROTTLE behavior. A finite positive ownership/forward-progress check did not complete within 20 seconds and had no accepted/dispatched per-task records at the captured ownership point. Therefore no ORCHESTRA performance superiority claim is made. The CFS baseline completed 12/12 short fixed-work runs and a matched 10-billion-iteration diagnostic in 5,036 ms. A three-second CFS stress smoke passed its workload phases; ORCHESTRA stress and comparison scripts were not executed because their ownership and cleanup assumptions were not safe for this host.

Highest gate reached: G21, with G9/G16 INCONCLUSIVE and G10/G17/G18 blocked.  
P0/P1/P2/P3 findings: 0/1/4/1.

The referenced ORCHESTRA_OS_Real_World_Machine_Test_Checklist.docx was audited item by item. It contains 519 checklist items across Phases 0-26. The exhaustive mapping is CHECKLIST_AUDIT.csv and the phase summary is CHECKLIST_COVERAGE.md: 94 PASS, 39 INCONCLUSIVE, 178 BLOCKED, and 208 NOT IMPLEMENTED. Kernel installation, bootloader, reboot, and fallback-boot items are explicitly blocked by the real-machine safety boundary and are labeled ACTION REQUIRES USER APPROVAL where applicable.

## Machine Configuration

Evidence: environment/20260821-094317-host_inventory.stdout and environment/20260821-100249-final_host_health_after_stress.stdout.

- Kali GNU/Linux Rolling 2026.3; physical HP Pro Tower 280 G9 E PC.
- Intel Core i7-13700; 16 reported cores, 24 logical CPUs, one socket, SMT enabled.
- One NUMA node.
- 15 GiB RAM; 7.5 GiB swap.
- NVMe storage; at final check 25 GiB free on root, 38 GiB free on home, and 7.7 GiB free in /tmp.
- intel_pstate, powersave governor, hardware frequency range 800 MHz-4.10 GHz; boost active.
- Final package temperature 57 C; reported high trip 80 C and critical trip 100 C. NVMe composite 45.9 C.
- cgroup v2; bpffs, debugfs, and tracefs mounted.
- AppArmor loaded; SELinux disabled.
- Root execution was available through sudo -n. No package installation, reboot, bootloader change, security-policy change, or persistent system configuration change was performed.

Toolchain: clang 21.1.8, gcc 15.3.0, bpftool 7.7.0 using libbpf 1.7, make 4.4.1, pahole 1.31, Python 3.14.6. Optional perf and stress-ng are missing; stress, mpstat, pidstat, numactl, sensors, and cpupower are present. The exact tool inventory is environment/20260821-095810-final_tool_availability.stdout.

Pre-existing kernel health included ACPI BIOS warnings and an sslh-generator segfault before ORCHESTRA. Correlated ORCHESTRA-time kernel logs contain only sched_ext enabled/disabled messages; they contain no ORCHESTRA oops, panic, lockup, RCU stall, hung task, verifier error, or scheduler error.

## Repository State

The initial and final repository identity was recorded. The tracked diff is empty. The worktree was not clean because the campaign directory, an older real-world artifact directory, and pre-existing untracked bridge/loader/fixed_work binaries were present. No tracked source or test file was edited by this campaign. Final evidence: environment/20260821-095919-final_repo_state.stdout.

## Implementation Reality Map

| Component | Reality | Evidence and boundary |
|---|---|---|
| Stage7 sched_ext scheduler | KERNEL_PROTOTYPED | orchestra_scx_stage7.bpf.c; fresh object attached on running 7.0.12 |
| Userspace bridge and ABI maps | KERNEL_PROTOTYPED | orchestra_bridge.c and bridge ABI; status/publish/opt-in exercised |
| Map-pinning loader | KERNEL_PROTOTYPED | orchestra_loader.c; required loader used for all attaches |
| Task identity/state/telemetry | KERNEL_PROTOTYPED | exact identity, task state, task telemetry, global telemetry maps observed |
| RUN | KERNEL_PROTOTYPED | per-task effective RUN evidence; finite completion gate still inconclusive |
| YIELD | KERNEL_PROTOTYPED | per-task dispatch/effective counters observed |
| MIGRATE | KERNEL_PROTOTYPED | three repeats moved an affinity-allowed task to CPU 1 |
| SLEEP | KERNEL_PROTOTYPED | deferred/release path observed; no-early invariant incomplete |
| THROTTLE | KERNEL_PROTOTYPED | four-phase duty-cycle telemetry observed |
| Fallback/default | KERNEL_PROTOTYPED | absent/non-opted directives fell back to RUN; unsupported CLI action rejected before kernel |
| Signal bus and authenticated predictive frame | USERSPACE_VALIDATED | no equivalent kernel runtime implementation found |
| Predictor/Kalman output | USERSPACE_VALIDATED | no kernel predictor output exposed |
| S1/S2/S3/S4/Q | USERSPACE_VALIDATED | no valid kernel inputs for these metrics |
| Feedback controller | USERSPACE_VALIDATED | no kernel actuator/controller loop exposed |
| Full hybrid RT safety | SPECIFIED / partial prototype | no sufficient runtime bypass/interoperability evidence |
| Multi-core coordination | KERNEL_PROTOTYPED / limited | local CPU migration exercised; no architectural coordination metric |
| NUMA-aware scheduling | SPECIFIED / unvalidated | host has one NUMA node and source has no validated NUMA policy |
| Distributed/node/cluster tier | SPECIFIED | not present/testable on one host |
| Deployment readiness | NOT IMPLEMENTED as a claim | no deployment claim is supported |

The canonical action set remained exactly RUN, SLEEP, MIGRATE, THROTTLE, and YIELD.

## Kernel Capability Assessment

The existing sanity script passed: benchmarks/real-machine/sanity_check.sh output is kernel/20260821-094519-sanity_check.stdout. The repository kernel configuration check passed: kernel/20260821-094521-kernel_config_check.stdout.

Required running-kernel options CONFIG_BPF, CONFIG_BPF_SYSCALL, CONFIG_BPF_JIT, CONFIG_DEBUG_INFO_BTF, CONFIG_SCHED_CLASS_EXT, and CONFIG_BPF_EVENTS were present. /sys/kernel/btf/vmlinux was present with SHA-256 3f39484930b332629a5864a1a703b0a39320cc1584f6e8a00dfbc6375b58ec76. The exact Linux 7.0.12 source tree used for the BPF compile was recorded in build/20260821-094617-exact_kernel_source_check.stdout.

Before the first attach, sched_ext was disabled, /sys/fs/bpf had no ORCHESTRA pins, and unrelated systemd BPF programs/maps/links were inventoried. They were preserved. The pre-load snapshot is scheduler/20260821-095004-pre_load_snapshot.stdout.

## Build Results

The documented userspace sequence was run as separate logged commands: make clean, make, make check, and make test. All returned zero. The make test output reports 30/30 named unit tests in the compiler/reference passes, generation-publication stress passes, bridge parser/ABI passes, sched_ext source-safety invariants, integration MAP_SHARED publication scenarios, and CSV validator scenarios.

A fresh vmlinux.h was generated from the running kernel BTF. The BPF object, bridge, loader, and fixed_work were compiled outside the source tree. The direct userspace link used installed libbpf/libelf/zlib libraries because pkg-config was absent; no dependency was installed. Build logs are build/20260821-094745-generate_vmlinux_h.stdout, build/20260821-094755-bpf_compile.stdout, build/20260821-094801-bridge_compile.stdout, build/20260821-094804-loader_compile.stdout, and the corresponding stderr files.

Fresh artifact hashes:

- vmlinux.h: 96b223c8eaa9763f6caa0998188cf632aa0133c096bf526edc0043db3e675a51
- orchestra_scx_stage7.bpf.o: 4b77ee093b157870cc075a851e25b41a8a370547bd9c5e1d12c611b506b363bd
- orchestra_bridge: 5d9caadd45328f5760f6cbbae959b8b0f020ef54513cc669853825525c56f745
- orchestra_loader: f420363ea67f4301d69ca37189ee613bbf3d6b340889846d204d96558cec6e5d
- fixed_work: a521006feb29fff5203e440a47dc8708b0c73c65b326304db59bbc7d31060504

## Static and Verifier Results

Static inspection found the expected init, exit, enable, disable, select_cpu, enqueue, dispatch, running, and stopping struct_ops sections; the expected maps; .BTF and .BTF.ext; and the stage7 ABI symbols. Full output, file types, hashes, ELF sections, symbols, and BTF map schemas are in verifier/20260821-094817-artifact_static_validation.stdout.

The map-pinning loader successfully opened and attached the object on three attempts. This is positive verifier/relocation/registration evidence. No verifier rejection occurred, so there is no rejected-program verifier log to reproduce or quote. Loader output for the first attach is scheduler/20260821-095013-scheduler_load_attempt1.stdout.

## Scheduler Load, Ownership, and Lifecycle

Load attempt 1 returned zero, enabled sched_ext, populated only the ORCHESTRA pin directory, and exposed ABI 2 / SCX API 70012 through the bridge. The first unload returned zero and removed ORCHESTRA state.

Load attempt 2 again reached enabled state; scheduler/20260821-095704-scheduler_post_load2.stdout shows the expected struct_ops programs and link. Safe invalid-PID and invalid-CPU publications were rejected while the scheduler remained enabled. The second unload returned zero.

Load attempt 3 was used for a finite forward-progress check. The worker did not complete inside the timeout, so the phase was stopped. The loader then unloaded cleanly. The final lifecycle snapshot is recovery/20260821-100033-post_unload_snapshot3.stdout.

The negative ownership check showed a non-opted worker without an exact task identity telemetry record while fallback telemetry increased. The positive long-lived worker showed exact identity, generation, accepted, dispatched, running, and effective counts for RUN, YIELD, and MIGRATE. The finite positive worker differed: its publication returned an identity/generation, but the immediate status snapshot had zero task accepted/dispatched counts and no exact task telemetry line. This is why G9 and G16 are INCONCLUSIVE rather than performance results.

## Functional Test Matrix

The authoritative row-level matrix is TEST_RESULTS.csv. Key outcomes:

- RUN: PASS. A positive exact-TID snapshot showed accepted=344, dispatched=344, running=346, effective=346, fallback=0.
- YIELD: PASS. A positive exact-TID snapshot showed accepted=1387, dispatched=1387, running=1391, effective=1391, fallback=0.
- MIGRATE: PASS for the tested affinity-allowed CPU 1 target. Three repeats showed the task on CPU 1 and effective migration counts; global migrate target and dispatch counters agreed.
- SLEEP: INCONCLUSIVE. A same-shell timeline published a two-second future deadline, showed deferred counts before the deadline, and showed the release count after it. It did not independently prove no CPU execution before the deadline. The unchanged directive then generated bad-parameter fallback behavior.
- THROTTLE: PASS for the tested 1-second period / 200-ms budget. Four one-second observations gave runtime increments of approximately 222 ms, 175 ms, 220 ms, and 195 ms, close to the requested 20 percent duty cycle. Prior SLEEP fallback counters were not attributed to this result.
- Fallback: PASS for the observed non-opted/no-directive path. The full-switch scheduler continued fallback dispatch rather than leaving tasks stranded.
- Invalid input: PASS as bridge input validation. Unknown action returned 1, invalid PID returned 6, and illegal CPU returned 7. These are not cryptographic integrity tests or runtime unknown-action injection tests.

## Baseline Results

The corrected native CFS baseline used fixed_work with 80,000,000 iterations, workers 1/2/4/8, and three repetitions per worker count. All 12 runs completed. Summary:

| Workers | N | Mean ms | Median ms | Min ms | Max ms | Sample SD ms |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 3 | 86.00 | 83 | 83 | 92 | 5.20 |
| 2 | 3 | 84.00 | 84 | 83 | 85 | 1.00 |
| 4 | 3 | 84.67 | 84 | 84 | 86 | 1.15 |
| 8 | 3 | 86.00 | 85 | 84 | 89 | 2.65 |

Raw corrected data is baseline/20260821-094943-baseline_fixed_work_retry2.stdout. The first two malformed collection attempts were retained and excluded.

The matched diagnostic baseline for 10,000,000,000 iterations completed under CFS in 5,036 ms with the expected fixed_work return code 1. It is evidence that the finite ORCHESTRA timeout was not simply too short for this workload on this host.

## ORCHESTRA and Comparative Results

No valid comparable ORCHESTRA timing table was produced. The finite ORCHESTRA worker was terminated at 20 seconds without completion and without proven per-task ownership. The action telemetry runs used a long-lived task and were designed to prove action effects, not to serve as a matched performance benchmark.

The repository benchmark scripts were inspected but not run. benchmark_suite.sh and full_compare.sh contain hard-coded /home/vagrant paths and broad struct_ops/link or bpffs cleanup; running them would violate the state-preservation boundary on this host. scx_simple and perf are absent. Therefore the campaign does not support claims that ORCHESTRA is faster, slower, better, or worse than CFS.

## Stress and Robustness

The existing stress suite was run only in CFS mode for a three-second smoke phase. CPU stress with 24 workers, memory stress using 7,837 MB through installed stress, I/O stress with 12 files, and the mixed phase all completed with zero workload errors. The script health row reported one warning because its broad grep matched pre-existing ACPI BIOS lines; no ORCHESTRA or critical health event was correlated with the run. Copied raw output is stress/20260821-100155-cfs-smoke-output and the logged invocation is stress/20260821-100155-stress_suite_cfs_smoke.stdout.

The ORCHESTRA mode of that script was not run because it checks only sched_ext state and does not opt tasks into the scheduler. It would not establish ownership and would produce an invalid ORCHESTRA stress claim. Long-duration, progressive ORCHESTRA stress, and comparison runs remain BLOCKED.

## Kernel Log Findings

The only campaign-correlated scheduler messages were:

- 09:50:13 enabled
- 09:54:50 disabled
- 09:55:09 enabled
- 09:57:54 disabled
- 09:59:38 enabled
- 10:00:29 disabled

No ORCHESTRA verifier error, BPF error, scheduler error, oops, panic, lockup, RCU stall, or hung task was observed. ACPI and sslh-generator messages predate the first attach and were treated as host baseline findings. Full pre/post evidence is in environment/20260821-094437-kernel_health_before.stdout and environment/20260821-100249-final_host_health_after_stress.stdout.

## Telemetry Findings

The runtime exposes generation, identity, action, requested CPU, dispatched CPU, actual CPU, accepted, dispatched, running, effective, fallback, and error fields per task, plus global lifecycle, enqueue, dispatch, action, deferred, and scheduler-error counters. RUN/YIELD/MIGRATE observations had coherent per-task and global counter movement. SLEEP showed two deferred and two released entries with no release failures. THROTTLE showed accepted/deferred/release movement and runtime increments close to the requested budget.

Telemetry limitations are material. Global counters alone cannot prove ownership. The finite worker status did not expose an accepted/dispatched per-task record despite a successful publication response. The runtime does not expose enough information to compute valid kernel S1/S2/S3/S4/Q, prediction error, controller response, cryptographic freshness, or full RT safety metrics, so none of those were fabricated.

## Failures and Root Causes

Detailed symptom/reproduction/diagnosis/recommendation records are in FINDINGS.md.

Priority summary:

| Priority | Finding | Classification |
|---|---|---|
| P0 | None | No system-stability event |
| P1 | Finite positive ownership/forward progress not met | INCONCLUSIVE_OWNERSHIP_NOT_PROVEN; root cause not isolated |
| P2 | SLEEP no-early and one-shot semantics incomplete | INCONCLUSIVE action validation |
| P2 | Valid performance/stress comparison path blocked | Missing tools and unsafe existing script assumptions |
| P2 | Kernel research layers absent | Not implemented in this revision |
| P2 | Single-node topology and limited causal observability | Scope limitation; no Q/scalability claim |
| P3 | Two malformed initial baseline CSV attempts | External evidence harness issue; corrected and preserved |

No recommended correction was applied.

## Required Fixes and Retest Advice

1. Ownership/forward progress: inspect the existing bridge admission and scheduler enable/enqueue sequence for the exact finite worker; establish a positive per-task record before timing. Retest with the same CFS diagnostic and a clean lifecycle. Do not accept publication return code as ownership.
2. SLEEP: define one-shot directive clearing or refresh behavior and add an independent no-early execution measurement. Retest before claiming SLEEP.
3. Benchmark/stress harness: make paths location-independent, remove broad cleanup, and require opt-in plus per-task ownership for ORCHESTRA rows. Install perf/scx_simple/stress-ng only with approval if needed.
4. Research features: implement and instrument kernel signal/predictor/coordination/controller/RT/NUMA/distributed layers before moving their claims beyond userspace or specification status.

## Research Interpretation

Proved by this campaign: the existing stage7 prototype compiles against the running 7.0.12 BTF, passes the loader/verifier/attach path, becomes the active sched_ext scheduler, records lifecycle and action telemetry, can produce effective RUN/YIELD/MIGRATE behavior for a proven long-lived task, exposes deferred SLEEP and budgeted THROTTLE paths, and unloads cleanly.

Partially supported: fallback behavior, SLEEP deferred release, THROTTLE duty-cycle behavior, and the negative/positive ownership model. The finite ownership/forward-progress anomaly prevents a stronger general workload claim.

Not proved: performance superiority, long-duration stability, full multi-worker forward progress, kernel predictive coordination, cryptographic signal integrity, S1/S2/S3/S4/Q, feedback control, full real-time hybrid safety, NUMA-aware scheduling, distributed scalability, or deployment readiness.

Simulation and userspace test results remain separate evidence classes. They were not copied into real-machine claims.

## Final Gate Table

The machine-readable table is CHECKLIST_STATUS.csv.

| Gate | Verdict | Short evidence |
|---|---|---|
| G0 | PASS | Commit and repository root recorded |
| G1 | PASS | Host/kernel/tool inventory complete |
| G2 | PASS | sched_ext support and config pass |
| G3 | PASS | BTF/eBPF prerequisites pass |
| G4 | PASS | Required toolchain pass; optional tools noted |
| G5 | PASS | Userspace and fresh BPF build pass |
| G6 | PASS | Loader attach reached verifier/registration |
| G7 | PASS | Scheduler registered on three attempts |
| G8 | PASS | Three clean lifecycle unloads |
| G9 | INCONCLUSIVE | Finite positive ownership/progress not proven |
| G10 | BLOCKED | Escalation stopped after G9 anomaly |
| G11 | PASS | RUN per-task effective telemetry |
| G12 | PASS | YIELD per-task effective telemetry |
| G13 | PASS | Fallback/no-directive path observed |
| G14 | PASS | Safe detach/recovery |
| G15 | PASS | 12/12 native CFS baseline rows complete |
| G16 | INCONCLUSIVE | No valid completed ORCHESTRA benchmark |
| G17 | BLOCKED | Comparison tools/scripts unavailable or unsafe |
| G18 | BLOCKED | Only CFS stress smoke was ownership-valid |
| G19 | PASS | Exposed telemetry cross-checks pass; scope limited |
| G20 | PASS | No correlated ORCHESTRA kernel health fault |
| G21 | PASS | No tracked-source diff |

## Next Recommended Experiment

The smallest high-information next test is a single exact-TID ownership retest using an existing safe protocol that waits for positive per-task enable/enqueue/running telemetry before starting a shorter fixed-work run. Compare it with the already captured 5,036-ms CFS diagnostic, then stop if the exact record again remains at zero. Do not begin performance or stress escalation until that gate is resolved.

## Evidence Index

- Full command/return/stdout/stderr log: COMMANDS.log
- Referenced DOCX checklist item audit: CHECKLIST_AUDIT.csv
- Referenced DOCX checklist phase summary: CHECKLIST_COVERAGE.md
- Repository and host evidence: environment/
- Build and hashes: build/
- Kernel/BPF evidence: kernel/ and verifier/
- Scheduler and lifecycle evidence: scheduler/ and recovery/
- Workload/action evidence: workloads/
- Telemetry evidence: telemetry/
- Baseline evidence: baseline/
- Stress evidence: stress/
- Machine-readable gate matrix: CHECKLIST_STATUS.csv
- Machine-readable test matrix: TEST_RESULTS.csv
- Structured result summary: RESULTS.json
