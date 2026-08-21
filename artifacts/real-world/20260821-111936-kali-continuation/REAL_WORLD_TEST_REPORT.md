# ORCHESTRA-OS real-world test report

## 1. Executive Summary

Campaign `20260821-111936-kali-continuation` tested commit `82f69cbac2d9bf4ffa1372550f73d9c2c084b8f9` on physical host `kali`, kernel `7.0.12+kali-amd64`.

Final classification: `PARTIALLY_VALIDATED`; overall claim class: `KERNEL_PROTOTYPED`. The userspace build/regression gate, sched_ext capability gate, fresh BPF/bridge build, scheduler load/unload, selected per-task action paths, positive ownership run, fault rejection, and CFS baseline passed. The broader acceptance objective did not pass.

The item-level audit covers all 519 approved checklist items:

- PASS: 94
- FAIL: 0 checklist items
- BLOCKED: 386, including 208 `BLOCKED_NOT_IMPLEMENTED`
- INCONCLUSIVE: 39
- N/A: 0

No critical safety event occurred. The most important unresolved result is the ORCHESTRA comparison ownership gate: only 2 of 9 timed rows showed positive exact-TID ownership for every target task. Those elapsed values are retained as raw evidence and are not treated as ORCHESTRA performance measurements.

## 2. Scope

Executed or inspected: repository inventory, machine inventory, build/regression, kernel/BPF readiness, fresh BPF/bridge/workload build, safe scheduler load/unload, exact-TID ownership, canonical actions, invalid-input handling, CFS baseline, a bounded manual comparison matrix, failure/recovery checks, kernel health, and final cleanup.

Not executed or not claimable: kernel installation/reboot, broad benchmark scripts with unsafe cleanup/path assumptions, bounded full stress suite, `scx_simple` comparison, `perf` counters, RT coexistence, kernel signal/predictor/controller/Q layers, cross-node NUMA, distributed scheduling, long-duration stability, and dynamic architecture validation.

The campaign followed the repository boundary: no ORCHESTRA implementation, test, kernel/BPF, or benchmark source was edited or created.

## 3. Source/Requirement Basis

Interpretation used, in order: repository architecture/ADR material, research and Work Package claims, root `AGENTS.md`, kernel documentation, approved checklist, existing scripts, current implementation, then general Linux knowledge.

The paper and userspace research tests were treated as design/simulation or userspace evidence. They were not promoted to kernel validation. The full checklist was normalized to the required status vocabulary in [CHECKLIST_STATUS.csv](CHECKLIST_STATUS.csv); absent kernel features use `BLOCKED_NOT_IMPLEMENTED` as the reason code.

## 4. Hardware

Evidence: `environment/host_inventory.stdout` from the preceding inventory and `recovery/final_health.stdout` from this continuation.

- HP Pro Tower 280 G9 E PCI Desktop PC.
- Intel 13th Gen Core i7-13700: 16 physical cores, 24 logical CPUs, 1 socket, SMT enabled.
- One NUMA node.
- 15 GiB RAM and 7.5 GiB swap.
- Approximately 25 GiB free on root and 7.7 GiB free on `/tmp` at final capture.
- CPU governor: powersave; reported hardware range 800 MHz–4.10 GHz.
- Network: `eth0`, 1 Gb/s link, `10.30.10.187/25`.
- Final package temperature: approximately 48°C; reported high trip 80°C and critical trip 100°C.

## 5. Software

- Kali GNU/Linux Rolling 2026.3.
- Running kernel: `7.0.12+kali-amd64`.
- Known fallback kernels: `6.16.8+kali-amd64` and `7.0.12+kali-amd64` were present; no reboot was performed.
- GCC 15.3.0, Clang 21.1.8, GNU Make 4.4.1.
- bpftool 7.7.0 with libbpf 1.7.
- Python 3.14.6.
- Present: `stress`, `numactl`, `lstopo-no-graphics`, `sensors`, `cpupower`, `mpstat`, `pidstat`, `numastat`, `vmstat`.
- Missing: `perf`, `scx_simple`, `stress-ng`.
- Running-kernel BTF SHA-256: `3f39484930b332629a5864a1a703b0a39320cc1584f6e8a00dfbc6375b58ec76`.
- Fresh BPF object SHA-256: `3b5d8462beff4384a54ce8cb4528eb5e461694fe4a4660942050cf3a55985b79`.

The working tree was dirty before and during the campaign. Pre-existing changes and untracked artifacts are recorded in `environment/repo_state_final.stdout`; no tracked implementation/test/benchmark source was changed by this campaign.

## 6. Initial Machine Health

The pre-test logs contained host-level ACPI/PCI warnings and an unrelated `systemd-sslh-generator` segfault at approximately 09:31. These were recorded before ORCHESTRA and were not attributed to it. Later kernel logs contain sched_ext enable/disable records and unrelated perf sampling-rate warnings, but no ORCHESTRA oops, panic, RCU stall, hung-task event, or scheduler error.

## 7. Build and Regression Results

`make clean`, `make`, `make check`, and `make test` all returned 0. `make test` reported:

- 30/30 named unit tests passed.
- Signal publication generation stress passed.
- Bridge parser/ABI/publication-source tests passed.
- sched_ext source safety invariants passed.
- CSV validator outputs passed for baseline/orchestra/tamper/controller-tamper/signal-stop scenarios.
- Integration signal publication, contention/retry/death, tamper, controller-tamper, and signal teardown scenarios passed.

The first BPF compile attempt failed because a shell variable was expanded before the command and the kernel `scx/common.bpf.h` include path was absent. The corrected retry passed. Both outputs remain in `build/bpf_compile.stderr` and `build/bpf_compile_retry.stdout`; this was an invocation failure, not evidence of a source defect.

## 8. sched_ext Readiness

`sanity_check.sh` and `check_kernel_config.sh` returned 0. The running kernel exposed `CONFIG_SCHED_CLASS_EXT=y`, BTF, BPF syscall/JIT support, BPF events, and `/sys/kernel/btf/vmlinux`. The initial sched_ext state was disabled. Exact bpffs inventories were captured and unrelated BPF programs were preserved; no broad bpffs cleanup was used.

The existing source BPF object was compiled against the exact running-kernel source/BTF path. The existing bridge, loader, and `fixed_work` binary were compiled with `-O2 -Wall -Wextra -Werror`.

## 9. Scheduler Load/Unload

The fresh stage7 object loaded through the existing loader and registered `orchestra_scx_stage7` with ABI 2 and sched_ext API 70012. The scheduler was unloaded after the runtime phases. Three additional load/unload cycles passed:

- state became `enabled` after each load;
- state became `disabled` after each unload;
- exact ORCHESTRA pins and links were removed;
- after the RCU grace period, ORCHESTRA maps/programs were absent;
- no reboot was required.

Evidence: `sched_ext/scheduler_load_attempt1.stdout`, `recovery/load_cycle2.stdout`, `recovery/load_cycle3.stdout`, `recovery/state_after_unload2.stdout`, `recovery/state_after_unload3.stdout`, `recovery/final_health.stdout`.

## 10. Ownership

The positive ownership gate used the existing `fixed_work` binary, CPU 0 affinity, bridge opt-in, and RUN publication. At one second the exact task record showed `accepted=16 dispatched=16 running=16 effective=16 fallback=0`. At two seconds the raw map showed `accepted_count=40`, `dispatched_count=40`, `running_count=39`, `effective_count=39`, `fallback_count=0`. The workload completed without timeout; its `wait_rc=1` is the expected nonzero return from the existing `(x & 255)` workload result.

The separate comparison matrix used the same workload and affinity. Only 2 of 9 ORCHESTRA rows had all target tasks accepted and dispatched. Seven rows had missing or non-positive exact status evidence. Those rows are `INCONCLUSIVE_OWNERSHIP_NOT_PROVEN`; their timings are not valid scheduler performance results.

## 11. Action Validation

| Action | Result | Evidence and limits |
|---|---|---|
| RUN | PASS for controlled task | `actions/RUN_status_t05.stdout`: accepted 17, dispatched 17, running 17, effective 17, fallback 0. |
| YIELD | PASS for controlled task | `actions/YIELD_status_t05.stdout`: accepted 27, dispatched 27, running 26, effective 26, fallback 0; global yield dispatch counter increased. |
| MIGRATE | PASS for controlled cross-core request | `actions/MIGRATE_status_t05.stdout`: requested/dispatched CPU 1 and actual CPU 1; target migration telemetry increased and other-CPU movement remained 0. |
| THROTTLE | PASS under explicit low valid budget | `actions/THROTTLE_FORCE_t05_status.stdout`: deferred/throttled task state and deferred/release counters were observed. The 200 ms budget trial ended before reaching its threshold, so that trial is not used as evidence of effective throttling. |
| SLEEP | INCONCLUSIVE | The timeline showed no dispatch before the future deadline and release after it. Reuse of the expired one-shot directive generated later bad-parameter fallbacks; repeated lifecycle semantics remain unvalidated. |

Counters were interpreted separately as requested, accepted, dispatched, effective, and fallback. A request counter alone was not treated as proof of an effective action.

## 12. Hybrid Safety / RT

No `SCHED_FIFO`/`SCHED_RR` coexistence claim was made. The checked-out kernel prototype does not expose the research Hybrid Safety Layer or a verified RT bypass path. The 13 RT checklist items are `BLOCKED_NOT_IMPLEMENTED`; ordinary-task behavior cannot substitute for RT validation.

## 13. Signal / Integrity

Existing bridge checks for exact task identity, generation/lease, PID validity, and CPU validity. Invalid action syntax, invalid PID, and invalid CPU requests were rejected without taking down the scheduler. Userspace HMAC, frame, freshness, and tamper tests passed in `make test`.

There is no executable kernel cryptographically protected predictive signal frame or safe kernel tamper injector in this prototype. Therefore the kernel Signal Bus and cryptographic-integrity checklist items remain `BLOCKED_NOT_IMPLEMENTED`; CLI rejection is not promoted to cryptographic validation.

## 14. Prediction

Userspace predictor/calibration tests passed, but no real-machine kernel predictor output, horizon, confidence, or prediction-error stream is exposed by the stage7 scheduler. Stable/increasing/decreasing/periodic/bursty kernel predictor regimes were not run. Kernel predictor items remain `BLOCKED_NOT_IMPLEMENTED`.

## 15. Coordination

No real-machine S1, S2, S3, S4, or Q is reported. The required signal freshness, forecast divergence, eligible/exempt population, action coherence, and temporal-stability inputs are not exposed by the kernel prototype. Userspace metric tests passed but do not prove kernel coordination. The thundering-herd blind spot therefore cannot be assessed with a valid Q decomposition.

## 16. Controller

Userspace controller mapping, bounds, and tamper tests passed. No kernel controller update stream, deficient submetric, actuator selection, parameter evolution, or stabilization response is exposed. Kernel controller validation remains `BLOCKED_NOT_IMPLEMENTED`.

## 17. Baseline Performance

The controlled CFS matrix used 600,000,000 iterations, fixed CPU affinity, and three repetitions per worker count. All 9 rows completed:

| Workers | Raw elapsed ms | Mean ms | Median ms | Std. dev. ms |
|---:|---|---:|---:|---:|
| 1 | 313, 305, 306 | 308.00 | 306.0 | 4.36 |
| 2 | 307, 305, 305 | 305.67 | 305.0 | 1.15 |
| 4 | 305, 309, 308 | 307.33 | 308.0 | 2.08 |

Evidence: `baseline/cfs_matrix.csv`.

## 18. ORCHESTRA Performance

No broad ORCHESTRA performance claim is made. The manual matrix retained all raw rows, but its ownership gate passed only 2/9 rows. Raw means were 4,715.33 ms for one worker, 7,869.67 ms for two, and 11,839.0 ms for four; these values have high variance and are not comparable scheduler results until every timed task has proven ORCHESTRA ownership.

The separate positive ownership workload establishes that the bridge/scheduler can produce exact positive telemetry for a controlled task. It does not repair the invalid comparison rows.

## 19. Scheduler Comparison

`scx_simple` was unavailable. `perf` was unavailable. `benchmark_suite.sh` and `full_compare.sh` were inspected but not executed because they assume `/home/vagrant` and contain broad BPF cleanup paths that could disturb unrelated state. The available evidence is therefore CFS baseline plus an ownership-gated exploratory ORCHESTRA matrix, not a three-scheduler comparison.

## 20. Workload Results

- CPU: single-task and 1/2/4-worker CPU workloads were exercised. CFS completed all baseline rows; ORCHESTRA ownership was inconsistent in the comparison matrix.
- Memory: no high/near-exhaustion memory campaign was run; the existing stress script was unsafe at its fixed memory setting.
- I/O: prior safe script evidence exists in the earlier campaign, but no new full continuation I/O matrix is claimed.
- Network: no valid peer/loopback benchmark protocol was available for the architecture-specific items.
- Mixed workload: not run as an ownership-validating ORCHESTRA experiment.

## 21. Dynamic Behavior

No kernel signal/predictor/controller outputs exist for the required stable, ramp, drop, spike, periodic, alternating, and bursty timeline. The only validated event timelines are action-specific deadline/budget observations. Dynamic architecture items remain blocked.

## 22. Thundering-Herd / Stability

Action and migration counters are observable for selected tasks, but population-wide action transitions and S4 temporal stability are not exposed. The comparison matrix shows missing ownership in multiple-worker rows, but it is not sufficient to diagnose synchronized mass switching. No Q or S4 value is fabricated.

## 23. Fairness / Starvation

The positive single-task run and comparison anomalies do not provide a valid per-task fairness distribution. The ownership-invalid multi-worker rows contain a potential forward-progress concern, but no formal fairness index or starvation claim is made. Fairness/starvation items remain blocked or inconclusive as shown in the CSV.

## 24. Stress

The repository stress suite was inspected. On this host `/usr/bin/stress` is present, so the script would launch two VM workers each with approximately half of 15 GiB RAM, requesting about 15.4 GiB in total. Because the script has no safe memory-size parameter, the full CFS phase was blocked for safety. ORCHESTRA mode also does not opt workloads into the scheduler and cannot prove ownership. See `stress/STATUS.md`.

## 25. Fault / Recovery

Validated faults: invalid action syntax, invalid PID, and invalid CPU target were rejected; the scheduler remained enabled. Validated recovery: scheduler unload after workloads and three subsequent load/unload cycles returned to disabled, with exact ORCHESTRA objects removed after RCU cleanup. Not run: CPU hotplug, bridge process failure during active work, kernel-install failure, reboot recovery, and all unsafe broad cleanup paths.

## 26. Security / Integrity

Input validation, exact PID identity, CPU validation, generation/lease checks, and userspace tamper tests were observed. Kernel cryptographic signal integrity, replay protection of a predictive kernel frame, and authorization across a distributed tier were not implemented or safely injectable. These are separate claims and remain blocked.

## 27. Multicore

The host has 24 logical CPUs. A 1/2/4-worker matrix was attempted with identical workload and affinity. CFS passed all rows. ORCHESTRA ownership was proven in 2/9 rows, so the matrix does not establish 1/2/4-core scheduler performance or scaling. 8- and higher-worker levels were not run after the ownership issue was observed.

## 28. NUMA

The machine has one NUMA node. Topology was recorded; cross-node placement, migration, locality, and remote-access tests are not applicable on this host. No NUMA-aware kernel policy was found, so no WP8 validation claim is made.

## 29. Long-Duration Stability

No 10-minute, 30-minute, one-hour, or multi-hour ORCHESTRA run was started. The ownership gate and safe stress prerequisite were unresolved, and the repository prototype lacks the predictor/controller observability needed for drift analysis. Long-duration items remain blocked.

## 30. Statistical Analysis

The CFS baseline uses n=3 per worker count and reports raw values, mean, median, standard deviation, minimum, and maximum in the CSV. The ORCHESTRA matrix also has n=3 per worker count, but 7/9 rows fail ownership validation. It is exploratory diagnostic evidence only, not a stronger experimental claim. No outliers were deleted.

## 31. Findings and Root Causes

Detailed findings, evidence, reproducibility, alternative causes, confidence, impact, and recommendations are in [FINDINGS.md](FINDINGS.md). The principal findings are:

1. High: persistent multi-worker ownership-gate failure.
2. High: apparent timing inflation cannot be interpreted as scheduler performance.
3. Medium: SLEEP deadline/release works in one timeline, but one-shot expiry semantics remain incomplete.
4. Medium: existing stress script is unsafe at this host's fixed memory setting.
5. Medium: comparison scripts are not portable and lack ownership-validating execution.
6. Medium: most research architecture layers are not implemented in the kernel prototype.
7. Low: initial external command harness failures were preserved and corrected without source changes.

## 32. Checklist Completion

The exhaustive item-level result is [CHECKLIST_STATUS.csv](CHECKLIST_STATUS.csv). Counts use the repository-required status vocabulary. The prior campaign's separate `NOT IMPLEMENTED` category is represented as `status=BLOCKED` and `reason_code=BLOCKED_NOT_IMPLEMENTED`.

| Status | Count |
|---|---:|
| PASS | 94 |
| FAIL | 0 |
| BLOCKED | 386 |
| INCONCLUSIVE | 39 |
| N/A | 0 |
| Total | 519 |

## 33. Limitations

- No implementation changes were authorized by the repository governance instructions, so absent features remain absent.
- No reboot, kernel installation, bootloader change, or fallback-boot test was performed.
- The host has one NUMA node and no distributed peer.
- Optional `perf`, `scx_simple`, and `stress-ng` tools are absent; no packages were installed.
- Existing benchmark/stress scripts have path, cleanup, memory, or ownership limitations.
- Ownership evidence is strong for selected single-task actions but inconsistent in the multi-worker comparison protocol.
- Userspace research results are not kernel results.

## 34. Advice / Recommended Next Actions

1. Establish a stable exact-TID admission/enqueue/running ownership gate before any performance timing and investigate the first causal divergence.
2. Define repeatable SLEEP directive refresh/clear semantics and rerun multi-cycle sleep/wake validation.
3. Provide a portable benchmark harness that preserves unrelated BPF state, bounds memory/I/O, records all PIDs, and proves ownership.
4. Implement and instrument the kernel signal bus, predictor, S1/S2/S3/S4/Q, controller, RT safety, NUMA, and distributed layers before scheduling their acceptance tests.
5. After ownership is reliable, repeat at least five controlled runs per configuration for stronger performance claims and include valid per-task CPU/fairness evidence.
6. Run RT, multi-NUMA, network, and long-duration stages only on hosts with the required implementation and safe test infrastructure.

No code or configuration change was implemented by this campaign.

## 35. Final Evidence-Based Conclusion

This checkout is a loadable sched_ext stage7 kernel prototype with demonstrated selected action telemetry and clean lifecycle recovery. It is not a 100%-passing implementation of the full ORCHESTRA architecture. The evidence supports `PARTIALLY_VALIDATED` and `KERNEL_PROTOTYPED`, not `EXPERIMENTALLY_VALIDATED`, `DEPLOYMENT_READY`, or a claim that ORCHESTRA is faster or safer than Linux. Remaining BLOCKED, INCONCLUSIVE, and BLOCKED_NOT_IMPLEMENTED items are genuine scope, observability, ownership, tooling, topology, and safety limitations—not failures hidden by changing the implementation.
