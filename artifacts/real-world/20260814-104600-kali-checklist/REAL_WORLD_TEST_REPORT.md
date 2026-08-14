# ORCHESTRA-OS Real-World Test Report

Campaign `20260814-104600-kali-checklist`  
Consolidates `20260814-093036-kali`, `20260814-095200-kali-auth`, `20260814-102000-kali-7port`, `20260814-103600-kali-actions`  
Host `kali`  
Date 2026-08-14  
Implementation modified: **YES** (operator-authorized 7.0 sched_ext API port and bridge `--status` telemetry only)

## 1. Executive Summary

Campaign ID: 20260814-104600-kali-checklist  
Date: 2026-08-14  
Host: kali (HP Pro Tower 280 G9)  
ORCHESTRA revision: not a git repository; tree `/home/sharda/Downloads/ORCHESTRA-OS-main`  
Kernel: 7.0.12+kali-amd64  
sched_ext: **enabled** during kernel phases with `orchestra_scx_stage7`; **disabled** at close  
Overall result: **PARTIALLY_VALIDATED**

Checklist (98 rows): PASS 58, FAIL 3, BLOCKED 24, INCONCLUSIVE 10, N/A 3.

Critical findings: none.  
High findings: F6 (6.12 kfunc vs 7.0 BTF, later ported); F7 (DSQ 0 abort, later enum restore); F8 (canonical actions not shown effective).

Validated on this machine: userspace gate; CFS baselines and stress (after `stress`); 7.0-ported load/unload including 3/3 cycles; full-switch running counters; CLI/fault rejection; short FIFO coexistence.

Not validated: effective kernel RUN/SLEEP/MIGRATE/THROTTLE/YIELD; isolated opt-in; kernel Q/S1–S4; predictor; controller; Hybrid Safety Layer; HMAC kernel signal; scx_simple; orchestra 24-way stress; 10+ minute loaded run; NUMA-aware WP8; cluster; deployment.

Most important limitation: the BPF scheduler attaches and runs the whole machine in fallback RUN; published directives rarely match at enqueue.

Recommended next action: diagnose identity/snapshot matching; do not boot the in-tree 6.12.96 VBox bzImage (NVMe disabled).

## 2. Scope

Tested: inventory; userspace `make test`; sanity/kconfig; CFS benchmark_suite and full_compare; CFS stress 10s/30s; 24-way CFS 60s CPU; userspace paper-cpu including tamper; BPF compile; loader attach/detach; action publish; 4-worker 8s under full switch; CLI faults; unload-with-work; short SCHED_FIFO under load.

Not tested: `stress_suite.sh orchestra`; long-duration loaded scheduler; network suite; `scx_simple`; N≥5 kernel orchestra; destructive bpffs wipe scripts; WP8 NUMA policy; distributed tier; kernel HMAC/predictor/controller.

Why: missing infrastructure, BLOCKED_NOT_IMPLEMENTED in the kernel prototype, thermal headroom (package high=80°C), and scripts that `rm -rf /sys/fs/bpf/*`.

## 3. Source/Requirement Basis

Precedence: repository `AGENTS.md`, `docs/status/current-state.md`, ADRs, Stage-7 BPF comments (originally v6.12 API), research paper as **pre-kernel simulation** (not this machine’s kernel results), existing `benchmarks/real-machine/*`.

Paper Q/MSE values were not copied into kernel results. No kernel Q exists here.

Operator later authorized package install and a 7.0 BPF API port. That overrides the default “do not edit source” rule for those files only.

## 4. Hardware

- Chassis: HP Pro Tower 280 G9 E PCI Desktop PC, SKU 7C115AV, firmware F.33 (2025-06-27)
- CPU: 13th Gen Intel Core i7-13700; 24 logical CPUs; 1 socket
- NUMA: 1 node (CPU 0–23, 15 GB)
- RAM: 15 GiB; swap 7.5 GiB
- Storage: NVMe 476.9 G; Kali root 46G (~23G free); `/tmp` is 7.7G tmpfs
- Network: eth0 observed 10.30.10.187/25 during inventory
- Thermal: coretemp Package high=80°C crit=100°C; idle ~47–55°C; 24-way 60s ~79°C; 30s CFS stress ~77°C; closeout ~47°C

## 5. Software

- Distro: Kali GNU/Linux Rolling 2026.3
- Kernel: 7.0.12+kali-amd64 `#1 SMP PREEMPT_DYNAMIC Kali 7.0.12-2kali1 (2026-06-18)`
- Also present: `/boot/vmlinuz-6.16.8+kali-amd64` (not the campaign kernel)
- gcc 15.3.0, clang 21.1.8, GNU Make 4.4.1, Python 3.13.14
- After authorization: bpftool, libbpf-dev, libelf-dev, linux-headers, linux-source-7.0, stress, numactl, linux-cpupower
- `scx_simple` not installed
- BTF vmlinux SHA-256: `3f39484930b332629a5864a1a703b0a39320cc1584f6e8a00dfbc6375b58ec76`
- BPF object SHA-256: `ba82987fb2aa09d1746c7dbc1937830965182612c23377fd61c3ee75fc38dab4`
- Bridge SHA-256: `5d9caadd45328f5760f6cbbae959b8b0f020ef54513cc669853825525c56f745`
- Loader SHA-256: `f420363ea67f4301d69ca37189ee613bbf3d6b340889846d204d96558cec6e5d`

## 6. Initial Machine Health

Before any ORCHESTRA load: sched_ext disabled; bpffs empty. Idle ~99%.

Pre-existing (not ORCHESTRA): ACPI BIOS errors (CreateField length zero; AE_AML_BUFFER_LIMIT); hp_bioscfg invalid command; journal time jumped backwards at boot. Stress-suite `BUG` grep matches ACPI `BIOS Error` (F-ACPI).

At close: sched_ext disabled; `/sys/fs/bpf` empty except the mount; `/tmp` 1% used.

## 7. Build and Regression Results

Command: `make clean && make && make test` from repo root. Duration ~33 s. Return codes 0/0/0.

- Named unit tests: 30/30 on four compiler passes
- Benchmark-validator / python suites: 21+4+34 as recorded in the first campaign
- Integration: 5 scenarios PASS (baseline, orchestra, tamper, controller-tamper, signal-stop)

Userspace paper-cpu (4 workers, 4s, seed 104729): baseline last-row Q=1.0 (N=3); orchestra Q ~0.79 / 0.52 / 0.30; tamper `rejected_frames=32`, Q=0. Class: **USERSPACE_VALIDATED only**.

## 8. sched_ext Readiness

- `CONFIG_SCHED_CLASS_EXT=y`
- `CONFIG_DEBUG_INFO_BTF=y`; `/sys/kernel/btf/vmlinux` present
- BPF syscall/JIT as required by `check_kernel_config.sh`
- `sanity_check.sh` exit 0 (initially printed bpftool MISSING; later installed)
- Running kernel is **7.0.12**, not the project’s 6.12.96 VBox artifact
- In-tree `artifacts/kernel-v6.12.96-orchestra-stage8.bzImage`: `CONFIG_BLK_DEV_NVME is not set` — **must not be installed** on this NVMe host

## 9. Scheduler Load/Unload

Required method: `sudo ./bridge/orchestra_loader --load ./orchestra_scx_stage7.bpf.o` (pins `/sys/fs/bpf/orchestra/*` before struct_ops attach). Bare `bpftool struct_ops register` is insufficient for the timer map.

Historical FAIL: 6.12 object vs 7.0 BTF (`scx_bpf_dispatch` missing).

Historical FAIL: first 7.0 insert-port attach, DSQ 0 runtime error.

After enum restore: load → `/sys/kernel/sched_ext/state=enabled`, `switch_all=1`, `scx_api=70012`. Unload → `disabled (unregistered from user space)`.

This session: **3/3** load/unload cycles, all rc=0.

## 10. Ownership

Full switch: `running` already thousands within ~1s of load (cycle1 running=2745). Workload 4×8s: `owned_4w_8s_ms=7997 ctx_delta=231675`.

`--opt-in` admits a TID. That is **not** proof the published directive is the one applied at enqueue.

`fallback` ≈ `running` while most tasks have no directive.

Classification: full-switch **KERNEL_PROTOTYPED** ownership of the machine; isolated opt-in **INCONCLUSIVE_OWNERSHIP_NOT_PROVEN**.

## 11. Action Validation

Canonical set tested via existing bridge `--publish` (no new test programs).

| Action | Requested | Accepted (typical) | Effective |
|---|---|---|---|
| RUN | yes gen=1 | not per-wakeup | INCONCLUSIVE (system fallback RUN) |
| YIELD | yes | ~+1 | INCONCLUSIVE |
| SLEEP | yes 2s not-before | 0 | FAIL (sleep_acc=0 deferred=0) |
| THROTTLE | yes | later 1 | INCONCLUSIVE |
| MIGRATE | yes cpu=3 | 0 | FAIL (CPU stayed 0; mig_acc=0) |

A request counter increment is not an effective action. See F8.

## 12. Hybrid Safety / RT

Paper Hybrid Safety Layer: **BLOCKED_NOT_IMPLEMENTED**.

Host `sudo chrt -f/-r` works. Under loaded ORCHESTRA, `sudo chrt -f 20` showed `SCHED_FIFO` priority 20; scheduler remained enabled until clean unload. No RT load, inversion, or exemption-counter study. Status: INCONCLUSIVE for coexistence; not a Hybrid Safety PASS.

## 13. Signal / Integrity

Kernel authenticated predictive frame: **BLOCKED_NOT_IMPLEMENTED**.

Userspace HMAC path and `--tamper-every`: PASS as USERSPACE_VALIDATED.

Kernel tamper: **BLOCKED_NO_SAFE_INJECTION_INTERFACE**.

Bridge CLI rejects unknown action, missing PID, missing maps, invalid PID, invalid CPU, stale SLEEP not-before. That is **input validation**, not cryptographic integrity.

## 14. Prediction

Kernel predictor outputs: **BLOCKED_NOT_IMPLEMENTED**. Userspace predictor columns: USERSPACE_VALIDATED. Simulation Kalman failure is **not** a measured result on this host.

## 15. Coordination

Kernel S1/S2/S3/S4/Q: **BLOCKED_NOT_IMPLEMENTED**. No kernel Q is reported. Userspace last-row Q on 4s runs is exploratory USERSPACE_VALIDATED only.

## 16. Controller

Kernel feedback controller: **BLOCKED_NOT_IMPLEMENTED**. Userspace controller columns exist in paper-cpu CSV.

## 17. Baseline Performance

Linux/CFS, same machine:

- `benchmark_suite.sh` N=3, 1/2/4 workers × 8s (inner loop uses whole-second `date +%s`; 1-worker elapsed sometimes &lt;8000 ms — script behavior, not a speedup claim)
- `full_compare.sh` CFS cpu+mixed 1–8 × 30s; e.g. cpu_8w 29940 ms, ctx 2394746
- 24-way 60s CPU: completed; package ~79°C

## 18. ORCHESTRA Performance

One 4-worker 8s run while loaded: 7997 ms vs CFS ~7993 ms. Full-switch, n=1. **INCONCLUSIVE_OWNERSHIP_NOT_PROVEN** as an isolated ORCHESTRA vs CFS ranking. Do not use README overhead estimates.

## 19. Scheduler Comparison

CFS: measured. `scx_simple`: **BLOCKED_MISSING_TOOL**. ORCHESTRA: attach proven, comparative ranking **not** claimed.

`full_compare.sh` ORCHESTRA branch was not used (script cleanup can wipe bpffs).

## 20. Workload Results

- CPU 1/2/4/8 CFS: PASS (existing scripts)
- CPU = 24 CFS 10s/30s suite: PASS after `stress`; 60s CPU-only PASS
- CPU &gt; nproc: N/A (no existing oversubscribe script)
- Memory: first suite FAIL (tmpfs); retry PASS with `stress` (7837 MB class in script accounting)
- I/O: PASS on 10s/30s CFS suite retry
- Mixed: CFS full_compare PASS; suite mixed PASS
- Network: **BLOCKED_MISSING_TEST_INFRASTRUCTURE**
- Near-exhaustion / OOM: **BLOCKED_FOR_SAFETY**
- Bursty CPU kernel path: **BLOCKED_MISSING_TEST_INFRASTRUCTURE**

## 21. Dynamic Behavior

Userspace ticks show S*/Q change. Kernel timeline (workload → signal → predictor → directive → effect) **not** observable. **BLOCKED_INSUFFICIENT_OBSERVABILITY** / not implemented.

## 22. Thundering-Herd / Stability

Kernel S4 / action-switch rate: **BLOCKED_NOT_IMPLEMENTED**. No evidence of a migration storm in MIGRATE counters (they stayed 0). That is absence of accepted migrates, not proof of good S4.

## 23. Fairness / Starvation

No per-task CPU-time matrix under isolated ORCHESTRA ownership. **BLOCKED_INSUFFICIENT_OBSERVABILITY**.

## 24. Stress

| Run | Mode | Result |
|---|---|---|
| 10s first | cfs, no stress | FAIL memory tmpfs |
| 10s retry | cfs | PASS (health WARN ACPI) |
| 30s | cfs | PASS (health WARN ACPI) |
| orchestra suite | 24-way | **BLOCKED_FOR_SAFETY** (thermal + ineffective actions) |

## 25. Fault / Recovery

| Trigger | Expected | Actual |
|---|---|---|
| `--status` no maps | error | rc=3 maps missing |
| `--publish` scheduler not orchestra | error | rc=2 |
| `--opt-in/--publish` PID 999999 | reject | rc=6 no identity record |
| MIGRATE CPU 99 | reject | rc=7 not allowed |
| SLEEP not-before=1 | reject | rc=7 next five seconds |
| Unload with live worker | disable, worker survives | rc=0; state disabled; worker_exit=0 |
| 3× load/unload | remain usable | 3/3 PASS |

No reboot required. No panic in campaign dmesg tails beyond the historical DSQ 0 abort (F7), which was recovered by unload.

## 26. Security / Integrity

Separated:

- Input validation: PASS (CLI)
- Process identity: invalid PID rejected
- Generation/freshness: SLEEP stale not-before rejected at CLI; kernel lease/expired counters stayed 0 during action tests (no matched path)
- Cryptographic integrity: **BLOCKED_NOT_IMPLEMENTED**
- Authorization: not a kernel HMAC/capability model in this prototype

## 27. Multicore

CFS 1/2/4/8 measured. ORCHESTRA 4 workers under full switch n=1. Not a 1/2/8/24 ORCHESTRA ownership matrix.

## 28. NUMA

Single node. WP8 NUMA-aware scheduling **BLOCKED_NOT_IMPLEMENTED**. `numactl` installed after authorization; topology remains one node.

## 29. Long-Duration Stability

10+ minute loaded run **BLOCKED_FOR_SAFETY** / not started. Short enabled intervals (seconds to about one minute in the action session) unloaded cleanly. Drift untested.

## 30. Statistical Analysis

CFS 8s exploratory N=3: 1-worker elapsed_ms min 7318, max 7965, mean 7569.7 (first campaign).

Kernel ORCHESTRA 4w 8s: n=1 (7997 ms). Actions n=1. **INCONCLUSIVE_INSUFFICIENT_SAMPLES** for any performance claim.

Userspace orchestra Q N=3: 0.79, 0.52, 0.30 — high variance; USERSPACE_VALIDATED exploratory only.

## 31. Findings and Root Causes

See `FINDINGS.md`. Order: F7, F8, F6 (HIGH); F2 (MEDIUM); F-ACPI (INFORMATIONAL).

No CRITICAL events. Campaign not STOPPED_FOR_SAFETY.

## 32. Checklist Completion

| Status | Count |
|---|---|
| PASS | 58 |
| FAIL | 3 |
| BLOCKED | 24 |
| INCONCLUSIVE | 10 |
| N/A | 3 |
| Total rows | 98 |

FAIL items: A8.3 MIGRATE effective; A8.5 SLEEP effective; M18.1 kernel MIGRATE placement (same evidence as A8.3). Historical F2 and F6/F7 were mitigated or retried and are not left as open checklist FAILs except the action effectiveness FAILs.

## 33. Limitations

- Kernel 7.0 port is not a 6.12 fidelity reproduction.
- Full `switch_all=1` prevents isolating ORCHESTRA-owned vs CFS tasks.
- Source invariant forbids `SCX_OPS_SWITCH_PARTIAL` in this BPF.
- No kernel Q, HMAC, predictor, or controller.
- Thermal ceiling near 80°C at 24-way.
- Dual-boot / NVMe host cannot use the VBox 6.12.96 artifact kernel.

## 34. Advice / Recommended Next Actions

IMPLEMENTATION CHANGE REQUIRED for identity/snapshot matching if developers want effective actions — **not implemented in this campaign**.

1. Compare bridge identity key bytes with BPF `task_identity(p)` on a live admitted TID.
2. Determine whether coherent snapshot failure is silent (`bad_id` stayed 0).
3. Keep using `orchestra_loader`; keep DSQ enum restore on 7.0.
4. Do not install `artifacts/kernel-v6.12.96-orchestra-stage8.bzImage` on this machine.
5. If 6.12 API fidelity is required, build a **custom 6.12.x kernel with NVMe**, do not use the VBox image.
6. Do not run 24-way orchestra stress until package stays well below 80°C or worker count is reduced by an existing script (do not patch the suite here).
7. Do not claim EXPERIMENTALLY_VALIDATED or DEPLOYMENT_READY.

## 35. Final Evidence-Based Conclusion

On this HP Pro Tower 280 G9, Kali 2026.3, Linux 7.0.12+kali-amd64, with the operator-authorized 7.0 port:

- Userspace ORCHESTRA is **USERSPACE_VALIDATED** by `make test` and short paper-cpu runs.
- The Stage-7 BPF scheduler is **KERNEL_PROTOTYPED**: it loads, runs the machine in full-switch, and unloads cleanly (3/3 cycles).
- Canonical kernel actions were **requested** and are **not experimentally validated**; MIGRATE and SLEEP were **not effective** as observed.
- Campaign decision: **PARTIALLY_VALIDATED**.
