# Stage 8 — Full Kernel Validation, Scaling, Reliability, and Security

Status: **In Progress**

## Scope

Stage 8 transforms the Stage 7 research implementation into a rigorously validated kernel-scheduling research platform through eight workstreams:

| Workstream | Description |
|-----------|-------------|
| 8A | Exact same-revision kernel/source/BTF/header alignment |
| 8B | Full kernel validation matrix (actions × states × failures) |
| 8C | Multi-core correctness and scaling |
| 8D | NUMA-aware placement |
| 8E | Long-duration reliability and soak tests |
| 8F | Fault injection and recovery |
| 8G | Reproducible benchmark methodology |
| 8H | Production-oriented security hardening |

## Baseline

| Component | Value |
|-----------|-------|
| Main commit | `4629a7f` |
| Stage 8 branch | `feature/stage8-full-kernel-validation` |
| Userspace | 25/25 unit, 34/34 validator, 5/5 integration |
| Stage 7 kernel env | Fedora 6.12.15 + v6.12.96 headers (compatible, not exact) |

## 8A — Exact kernel alignment

Target: Linux `v6.12.96`. Running kernel, source, BTF, vmlinux.h, sched_ext headers, official sample, and ORCHESTRA build must all originate from this same pinned revision.

Required steps:
1. Build v6.12.96 kernel from source with required CONFIG_ options
2. Boot in VirtualBox guest
3. Verify BTF, sched_ext state
4. Build scx_simple and ORCHESTRA from source
5. Validate 3-cycle official sample
6. Attach and validate ORCHESTRA

Status: **BLOCKED** pending VirtualBox guest kernel build. Fedora 6.12.15 kernel with v6.12.96 headers is runtime-validated compatible combination.

## 8B — Full validation matrix

Matrix dimensions: 5 actions × 6 controller states × 11 directive conditions × 11 lifecycle conditions.

Automated test runner at `kernel/sched_ext/scripts/reproduce_stage7_runtime.sh` validates the core path. Extension to full matrix deferred to exact-kernel environment.

## 8C — Multi-core scaling

Test configurations: 1/2/4/8 vCPU. Workloads: CPU-bound, mixed, short-burst, migration-heavy, throttled, deferred-eligibility.

Requires exact-kernel environment for controlled measurements. Expected outputs: throughput, completion time, fairness, tail latency, scheduler errors.

## 8D — NUMA placement

Current VirtualBox VM exposes single NUMA node. NUMA-aware placement implemented in source with capability detection. Runtime validation blocked pending multi-node topology.

Status: **BLOCKED** — no multi-node NUMA topology in current VM.

## 8E — Reliability

Tiered soak campaigns: 10-minute smoke, 60-minute reliability, extended multi-hour when environment permits.

During campaigns: publish new generations, rotate actions, create/exit disposable tasks, change controller states, read telemetry, verify scheduler health.

## 8F — Fault injection

Controlled faults: corrupted policy, wrong digest, stale generation, partial inactive slot, bridge death, loader death, invalid task identity, invalid CPU, affinity change, map update failure.

For each fault: verify safe RUN fallback, previous generation preserved, scheduler survival or clean disable.

## 8G — Benchmark methodology

Harness at `benchmarks/stage8/`. Includes workload generator, environment capture, trial runner, result validator, statistics summarizer.

VirtualBox results are VM results. Bare-metal requires dedicated test machine.

## 8H — Security hardening

Threat model at `docs/security/stage8-threat-model.md`. Covers: untrusted policy file, untrusted bridge args, malicious task identity, PID reuse, map tampering, privilege misuse, shell injection, path traversal, integer overflow.

CLI hardening: argument validation, policy path handling, file type/ownership checks, map schema validation, fixed-width arithmetic, generation overflow, privilege drop.

## Known Stage 8 limitations

- Exact kernel alignment requires guest kernel build (pending time/disk)
- NUMA placement blocked by single-node VM topology
- Bare-metal benchmarking requires suitable hardware
- Performance claims require controlled statistical evidence
- Production security certification not claimed
