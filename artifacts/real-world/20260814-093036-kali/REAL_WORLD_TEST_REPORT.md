# ORCHESTRA-OS Real-World Test Report

Campaign `20260814-093036-kali`  
Host `kali`  
Date 2026-08-14  
Implementation modified: **NO**

## 1. Executive Summary

Campaign ID: 20260814-093036-kali  
Date: 2026-08-14  
Host: kali (HP Pro Tower 280 G9)  
ORCHESTRA revision: not a git repository; tree `/home/sharda/Downloads/ORCHESTRA-OS-main`  
Kernel: 7.0.12+kali-amd64  
sched_ext: present, **disabled** throughout  
Overall result: **BLOCKED_BY_ENVIRONMENT**

Checklist (91 rows): PASS 37, FAIL 2, BLOCKED 49, N/A 3.

Critical findings: none.  
High findings: F1 kernel prototype cannot be built or loaded.

Validated: userspace build/test; running-kernel sched_ext *config*; CFS baselines; userspace paper-cpu telemetry including tamper rejection.  
Not validated: any ORCHESTRA-owned kernel scheduling.

Most important limitation: missing bpftool/libbpf-dev/kernel source and a 7.0 vs 6.12 sched_ext API gap.

Recommended next action: authorize toolchain packages and a matching 6.12.x kernel/source, then rebuild, load, prove ownership.

## 2. Scope

Tested: repository userspace gate; machine inventory; kernel Kconfig/BTF/sched_ext sysfs; CFS CPU/mixed workloads; 24-way CPU spin; userspace paper-cpu (baseline, orchestra, tamper); privileged RT policy set; existing benchmark/stress scripts where safe.

Not tested: BPF verify/load, ownership, kernel actions, kernel signal/Q/controller, scx_simple, orchestra-mode stress, network suite, NUMA-aware policy, long-duration loaded scheduler, cluster scale.

Why: environment blockers (tools/headers/source) and features the kernel prototype does not implement. Destructive `rm -rf /sys/fs/bpf/*` scripts were not run.

## 3. Source/Requirement Basis

Precedence used: repository `AGENTS.md` (this campaign), `docs/status/current-state.md`, ADRs, `kernel/sched_ext/orchestra_scx_stage7.bpf.c` comments (v6.12 API), research paper treated as pre-kernel simulation (not this machine’s results), existing `benchmarks/real-machine/*` scripts.

Paper Q/MSE values were not copied into real-machine kernel results. No kernel Q exists here.

## 4. Hardware

- Chassis: HP Pro Tower 280 G9 E PCI Desktop PC, SKU 7C115AV, firmware F.33 (2025-06-27)
- CPU: 13th Gen Intel Core i7-13700; 16 cores/socket, 2 threads (P-cores) + E-cores; 24 logical CPUs; 1 socket
- Caches: L3 30 MiB; hybrid L2 topology (hwloc)
- NUMA: 1 node (node0 = CPU 0–23, 15 GB)
- RAM: 15 GiB; swap 7.5 GiB
- Storage: NVMe 476.9 G, Kali root 46G (23G free), `/home` 43G
- Network: eth0 10.30.10.187/25, 1 Gbps when up
- Thermal: coretemp Package high=80°C crit=100°C; idle ~55°C; 24-way 60s ~79°C
- Missing tools: numactl, cpupower, perf, bpftool, scx_simple, stress, libbpf-dev

## 5. Software

- Distro: Kali GNU/Linux Rolling 2026.3
- Kernel: 7.0.12+kali-amd64 `#1 SMP PREEMPT_DYNAMIC Kali 7.0.12-2kali1 (2026-06-18)`
- cmdline: `BOOT_IMAGE=/boot/vmlinuz-7.0.12+kali-amd64 root=UUID=ba748417-bde3-40af-8f54-01947d49ffa8 ro quiet splash`
- gcc 15.3.0, clang 21.1.8, GNU Make 4.4.1, Python 3.13.14
- libbpf1 1.7.0 runtime `.so` only (no `libbpf.so` unversioned symlink / headers)
- ORCHESTRA: unpacked tree, `git` unavailable
- Userspace binary SHA-256: `eecd6c80a6c8470c3d8b759020b2e75213ed21a935cf4ce3d4dc0645184726b2`
- BTF vmlinux SHA-256: `3f39484930b332629a5864a1a703b0a39320cc1584f6e8a00dfbc6375b58ec76`

## 6. Initial Machine Health

sched_ext disabled. bpffs empty (`/sys/fs/bpf` only). Idle ~99%. Load 0.36 0.43 0.27.

Pre-existing (not ORCHESTRA): ACPI BIOS errors (CreateField length zero; AE_AML_BUFFER_LIMIT); hp_bioscfg invalid command; journal time jumped backwards at boot. No panic/RCU stall/hung_task in test-period dmesg tails.

## 7. Build and Regression Results

Command: `make clean && make && make test` from repo root.  
Duration: 33 s. Return codes: clean 0, make 0, test 0.

- Userspace binary built with `-Werror`.
- Named unit tests: 30/30 on four compiler passes (GCC and Clang, including legacy publication).
- Benchmark-validator: 21 tests OK.
- Signal-publication runner: 4 tests OK.
- CSV validator: 34 tests OK.
- Integration: MAP_SHARED stress + 5 scenarios (baseline, orchestra, tamper, controller-tamper, signal-stop) PASS.
- Clang static analyzer / scan-build: not present in the current `tests/` harness (README historical “0 analyzer findings” was not a separate tool run here). `make check` ran as part of `make test`.

BPF compile: FAIL/BLOCKED — `scx/common.bpf.h` not found.  
Bridge compile: FAIL/BLOCKED — `cannot find -lbpf`.

## 8. sched_ext Readiness

| Check | Result |
|---|---|
| `/sys/kernel/sched_ext` | present, state=disabled |
| CONFIG_SCHED_CLASS_EXT | y |
| CONFIG_DEBUG_INFO_BTF | y |
| BPF syscall/JIT | y |
| `/sys/kernel/btf/vmlinux` | 5.2M present |
| bpftool | **missing** |
| clang/gcc/make/python3 | present |
| Disk | 23G free on `/` |
| Kernel vs prototype | running 7.0.12; source targets v6.12 |

`sanity_check.sh` exit 0 while printing `[MISSING] bpftool`. Treat tool gap as a campaign blocker, not a silent PASS of kernel readiness.

## 9. Scheduler Load / Unload

Not executed. No BPF object, no bpftool. State remained disabled. `enable_seq=0`, `nr_rejected=0`.

Scripts `p0_ownership_retest.sh` and `stage8_validate.sh` perform `rm -rf /sys/fs/bpf/*`. They were **not** run. `reproduce_stage7_runtime.sh` assumes `$HOME/Documents/ORCHESTRA-OS` and `$HOME/src/linux-v6.12.96`.

## 10. Ownership

**INCONCLUSIVE_OWNERSHIP_NOT_PROVEN / BLOCKED.** No SCHED_EXT opt-in, no enqueue/running BPF counters. CFS results are Linux CFS/EEVDF, not ORCHESTRA.

## 11. Action Validation

Kernel RUN / YIELD / MIGRATE / THROTTLE / SLEEP: **BLOCKED_MISSING_TOOL**.

Userspace approximations: unit tests `bounded_run_action_execution`, `bounded_yield_action_execution`, `migrate_restores_affinity` passed. Paper-cpu CSVs show per-tick action counts. That is **USERSPACE_VALIDATED**, not kernel dispatch.

## 12. Hybrid Safety / RT

Kernel Hybrid Safety Layer: **BLOCKED_NOT_IMPLEMENTED** (current-state.md).

Host: unprivileged `chrt` → Operation not permitted. `sudo chrt -f 10` and `sudo chrt -r 10` succeeded (SCHED_FIFO/RR priority 10). This is Linux capability, not ORCHESTRA/RT coexistence.

## 13. Signal / Integrity

Kernel authenticated signal frame: **BLOCKED_NOT_IMPLEMENTED**. Bridge maps are not HMAC frames.

Userspace: HMAC path in unit/integration PASS. `--tamper-every 5` on this host: 40 data rows, `rejected_frames=32`, last-row S2=0, Q=0. Class: USERSPACE_VALIDATED.

No safe kernel tamper injector: **BLOCKED_NO_SAFE_INJECTION_INTERFACE**.

## 14. Prediction

Kernel predictor: **BLOCKED_NOT_IMPLEMENTED**.

Userspace CSV contains `cpu_pred`, `confidence`, `forecast_error`, `prediction_used`. 4s exploratory runs only. Not a real-machine Kalman study. Simulation identifiability failure is **not** claimed as a hardware result.

## 15. Coordination

Kernel S1–S4/Q: **BLOCKED_NOT_IMPLEMENTED**.

Userspace last-row (eligible_workers=4, interval 100ms, duration 4s, seed 104729):

| run | S1 | S2 | S3 | S4 | Q |
|---|---|---|---|---|---|
| baseline 1–3 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| orchestra 1 | 0.52397831 | 1.0 | 1.0 | 0.75000000 | 0.79176016 |
| orchestra 2 | 0.82058355 | 0.5 | 0.35398516 | 0.5 | 0.51911308 |
| orchestra 3 | 0.17720432 | 0.5 | 0.35398516 | 0.25 | 0.29757219 |
| tamper | 0.49221421 | 0.0 | 0.35398516 | 0.5 | 0.0 |

Formula in userspace: `Q = (S1*S2*S3*S4)^(1/4)` per implementation/docs. RT tasks: `--rt-exempt 0`. Population size 4. Sample interval 100ms. Do not report this as kernel Q.

## 16. Controller

Kernel controller: **BLOCKED_NOT_IMPLEMENTED**.  
Userspace controller columns present in v7 CSV (`controller_state`, saturation, actuators). Short runs; no kernel-loop causality claim.

## 17. Baseline Performance

Linux/CFS, same machine, `benchmark_suite.sh` default 8s, N=3:

| workers | elapsed_ms | ctx_delta |
|---|---|---|
| 1 | 7318, 7426, 7965 | 148016, 128545, 146725 |
| 2 | 7993, 7991, 7993 | 217714, 195849, 193069 |
| 4 | 7993, 7994, 7993 | 363784, 359023, 388546 |

`full_compare.sh` 30s CFS (one repetition):

| test | elapsed_ms | ctx_switches |
|---|---|---|
| cpu_1w | 29445 | 420766 |
| mixed_1w | 29997 | 63112 |
| cpu_2w | 29986 | 597936 |
| mixed_2w | 30002 | 448486 |
| cpu_4w | 29986 | 1251990 |
| mixed_4w | 30042 | 834343 |
| cpu_8w | 29940 | 2394746 |
| mixed_8w | 30047 | 1720380 |

1-worker 8s elapsed sometimes <8000ms because the inner loop uses whole-second `date +%s` bounds (script behavior, not a CFS speedup claim).

## 18. ORCHESTRA Performance

**Not measured.** Scheduler not loaded. Any timing without ownership would be `INCONCLUSIVE_OWNERSHIP_NOT_PROVEN`.

## 19. Scheduler Comparison

| scheduler | result |
|---|---|
| CFS | measured (sections 17) |
| scx_simple | BLOCKED_MISSING_TOOL |
| ORCHESTRA | BLOCKED_MISSING_TOOL |

`benchmark_suite.sh` logged `scx_simple not installed` and `BPF object missing: /home/vagrant/Documents/ORCHESTRA-OS/kernel/sched_ext/orchestra_scx_stage7.bpf.o`.

## 20. Workload Results

- CPU 1/2/4/8: CFS PASS (existing scripts).
- CPU = 24: 10s stock suite PASS; 60s CPU-only PASS; package 79°C.
- Memory stock suite: FAIL (tmpfs fill). Files removed afterward. `/tmp` restored to ~1% used. `/` still 23G free.
- I/O stock suite: not reached.
- Mixed: CFS full_compare PASS (small `/tmp` writes).
- Network: BLOCKED_MISSING_TEST_INFRASTRUCTURE.

## 21. Dynamic Behavior

Kernel timeline (workload → signal → predictor → directive → sched effect): **BLOCKED**.  
Userspace ticks show changing directive/S1–S4/Q in 4s CSVs. CFS still dispatches.

## 22. Thundering-Herd / Stability

Kernel action-switch/S4: **BLOCKED_NOT_IMPLEMENTED**.  
Userspace emits `S4_burst` and change fractions. Not kernel mass-switch evidence.

## 23. Fairness / Starvation

No ORCHESTRA-owned per-task CPU traces. **BLOCKED_INSUFFICIENT_OBSERVABILITY** for kernel fairness. CFS 8s/30s jobs completed; that is not an ORCHESTRA fairness index.

## 24. Stress

- `stress_suite.sh 10 cfs`: rc=1. CPU 10s PASS. Memory FAIL (F2). I/O/mixed/health not reached.
- Orchestra mode: not run (`sched_ext` disabled).
- 60s 24-way CPU-only: completed; no new kernel panic in dmesg tail; sched_ext still disabled.
- 60s full suite not repeated (tmpfs safety).

## 25. Fault / Recovery

Kernel fault campaign: **BLOCKED**. No invalid-PID bridge tests (binary not linked). Unload-while-loaded: N/A (never loaded). No reboot required.

## 26. Security / Integrity

Kernel crypto integrity: **BLOCKED_NOT_IMPLEMENTED**.  
Userspace tamper: PASS as userspace. CLI syntax rejection ≠ cryptographic kernel validation.

## 27. Multicore

CFS 1, 2, 4, 8 workers measured. 24-way CPU spin measured. These do **not** prove N-core ORCHESTRA ownership.

## 28. NUMA

Single NUMA node. `numactl` not installed. WP8 NUMA-aware scheduling **BLOCKED_NOT_IMPLEMENTED**. Topology recorded via `lscpu` and `lstopo-no-graphics`.

## 29. Long-Duration Stability

ORCHESTRA loaded long-run: **BLOCKED**.  
Longest CPU stress: 60s at 24 workers. Further 24-way load withheld (79°C vs 80°C high). Not a reliability certification.

## 30. Statistical Analysis

CFS 8s N=3 (exploratory minimum met for CFS only):

- workers=1 elapsed_ms: min 7318, max 7965, mean 7569.7
- workers=2: min 7991, max 7993, mean 7992.3
- workers=4: min 7993, max 7994, mean 7993.3

No ORCHESTRA sample. Do not compare a missing ORCHESTRA run to these CFS means. full_compare 30s is N=1.

Userspace orchestra last-row Q N=3: 0.792, 0.519, 0.298 — high variance; last-row statistic only.

## 31. Findings and Root Causes

See `FINDINGS.md`. Summary: F1 HIGH environment/toolchain/API; F2 MEDIUM stress tmpfs; F3 LOW userspace Q variance; F4 INFORMATIONAL Vagrant paths; F5 INFORMATIONAL ACPI pre-existing.

## 32. Checklist Completion

| status | count |
|---|---|
| PASS | 37 |
| FAIL | 2 |
| BLOCKED | 49 |
| INCONCLUSIVE | 0 rows (Q stability in T12u/F3) |
| N/A | 3 |
| **total** | **91** |

FAIL items: W13.6 memory stress_suite; ST15.1 stress_suite 10s complete.

## 33. Limitations

- No physical KERNEL_PROTOTYPED evidence on this host.
- Kernel 7.0.12 may require an approved sched_ext API review even after tools are installed (`orchestra_scx_stage7.bpf.c` forbids a compile-only rename).
- Host is dual-boot; not treated as a throwaway lab disk.
- Packages were not installed (campaign policy).
- Network, NUMA policy, cluster, loaded long-run untested.
- README “25 unit tests” is stale vs observed 30 named tests.

## 34. Advice / Recommended Next Actions

1. **Do not claim** this machine has run ORCHESTRA sched_ext.
2. If a physical kernel pilot is still the goal, obtain authorization to install: `bpftool`, `libbpf-dev`, `libelf-dev`; optionally `stress`, `numactl`, `linux-cpupower`, and an scx userspace scheduler package.
3. Supply kernel source/headers for the **intended** ABI. Prefer booting the project’s validated Linux 6.12.x with `CONFIG_SCHED_CLASS_EXT` rather than porting blindly to 7.0.12.
4. After build: pin only ORCHESTRA maps; do not run scripts that `rm -rf /sys/fs/bpf/*` if any other BPF exists.
5. Prove ownership (opt-in + enqueue/running counters) before any performance comparison.
6. Fix or replace stress memory path before 50%-RAM file writes to tmpfs (developer change; not done here).
7. Point benchmark scripts at repo-relative BPF/bridge paths.
8. Thermal: 24-way 100% approached Package high=80°C in 60s; use shorter or partial-CPU stress on this HP tower.

IMPLEMENTATION CHANGE REQUIRED for a 7.0 sched_ext port. IMPLEMENTATION CHANGE REQUIRED for portable bench paths and tmpfs-safe stress. No such changes were made in this campaign.

## 35. Final Evidence-Based Conclusion

On this Kali 7.0.12 HP i7-13700 host, the ORCHESTRA **userspace** gate passed and Linux/CFS baselines were recorded. The Stage-7 **kernel** scheduler was not compiled, not loaded, and did not own any tasks. The campaign decision is **BLOCKED_BY_ENVIRONMENT**. Claim class: **USERSPACE_VALIDATED** only. Not **EXPERIMENTALLY_VALIDATED**, not **DEPLOYMENT_READY**.
