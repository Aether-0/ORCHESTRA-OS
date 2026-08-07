# 6. Stage-by-Stage Report

## Stage 1 — Userspace Core Architecture

### Goal
Implement the paper-aligned real-CPU userspace prototype with cryptographic signal integrity, per-process adaptive response, and coordination metrics.

### Implementation
- **Source:** `orchestra_paper_cpu_demo/orchestra_paper_cpu.c` (3117 lines)
- **Key types:** `signal_payload_t`, `worker_state_t`, `coord_metrics_t`
- **Actions:** RUN, SLEEP, MIGRATE, THROTTLE, YIELD
- **Learning:** Tabular Q-learning (RL_ALPHA=0.20, RL_GAMMA=0.90)
- **Exploration:** Epsilon-greedy (START=0.30, MIN=0.02, DECAY=0.998)
- **Rewards:** +0.6 match / -0.6 mismatch + difference rewards
- **Jitter:** Perceptual anti-synchronization (JITTER_MULTIPLIER=1.50)
- **Signals:** 128-byte payload + 32-byte HMAC-SHA256
- **Metrics:** S1 (fidelity), S2 (compliance), S3 (coherence), S4 (stability)
- **Aggregation:** Geometric mean Q = (S1 × S2 × S3 × S4)^(1/4)

### Files
```
orchestra_paper_cpu_demo/
├── orchestra_paper_cpu.c    Main implementation
├── Makefile                 GCC + Clang builds
├── README.md               Documentation
├── sample_baseline.csv      Reactive reference output
├── sample_orchestra.csv     ORCHESTRA output
└── sample_tamper.csv        Signal tamper output
```

### Validation
- **Unit:** 25 named tests (sha256_hmac, serialization, frame_verification, directive_boundaries...)
- **Integration:** 5 scenarios (baseline, orchestra, tamper, controller-tamper, signal-stop)
- **Stress:** Generation-stamped publication 10,000+ iterations, 0 torn frames
- **GCC + Clang:** `-Wall -Wextra -Wpedantic -Wconversion -Wshadow -Wformat=2 -Werror`
- **Sanitizers:** ASan + UBSan with 0 findings
- **Analyzer:** Clang static analysis with 0 findings

### Results
| Metric | Value |
|--------|-------|
| Test count | 25 unit + 34 validator + 5 integration |
| Publication stress | 10,000+, 0 torn frames |
| Source SHA-256 | `5fc21224...` |
| Binary SHA-256 | `3a68b633...` |

---

## Stage 2 — Metrics Framework

### Goal
Establish strict append-only metrics contracts (v2→v6) with programmatic CSV validation.

### Implementation
- **Schemas:** `experiments/schemas/paper_cpu_metrics_v{2,3,4,5,6}.json`
- **Manifests:** `experiments/manifests/paper_cpu_exploratory_v{2,3,4,5,6}.json`
- **Validator:** `tests/integration/validate_paper_cpu_csv.py` (34 contract tests)
- **Benchmark runner:** `tools/benchmark/run_paper_cpu_benchmark.py` (21 tests)

### Metrics Evolution

| Version | Columns | New Fields |
|---------|---------|------------|
| v2 | 40 | Historical S1-S4 |
| v3 | 66 | S2_selected, S2_effective, S3_global, S3_conditioned |
| v4 | 83 | S4_burst, change_fraction, oscillation_penalty |
| v5 | 107 | Controller state machine diagnostics |
| v6 | 120 | Policy mode, generation, persistence |

### Key ADRs
- **0003:** Metrics v3 conditioned coherence
- **0004:** Effective userspace action metrics
- **0005:** Burst-sensitive temporal stability
- **0006:** Generation-stamped signal publication

---

## Stage 3 — Generation-Stamped Signal Bus

### Goal
Replace byte-wise atomic publication with C11-safe multi-reader transport.

### Implementation
- **Two-slot design:** `generation_signal_publication_t` with `publication_token`
- **Writer protocol:** odd sequence → write → even sequence → publish token
- **Reader protocol:** acquire token → pin slot → load words → verify → accept
- **Bounded retry:** 10 attempts max, safe fallback on exhaustion
- **Reader gates:** Bit 63 writer lease, lower bits reader pin count
- **Legacy path:** `-DORCHESTRA_SIGNAL_PUBLICATION_LEGACY=1` for equivalence testing

### Complexity
| Operation | Legacy | Optimized |
|-----------|--------|-----------|
| Publisher | O(160) byte stores | O(20) word stores + O(1) metadata |
| Reader | O(160) byte loads | O(retries × 20) word loads |

### Validation
- Publication canonical equivalence tests
- Deterministic fault injection (22 scenarios)
- Thread stress test: 4 readers, 2000 publications, 0 torn frames
- Process stress test: MAP_SHARED multi-process, 0 accepted duplicates

## Stage 4 — Controller Safety State Machine

### Goal
Convert the bounded multi-actuator controller into an explicitly stateful, observable, fail-safe control subsystem.

### Implementation
- **6 states:** NORMAL, DEGRADED, SATURATED, DISABLED, ROLLBACK, RECOVERY
- **Rolling windows:** 10-sample metrics, 8-sample actuator oscillation
- **Hysteresis:** Entry/exit thresholds differ; 3+ continuous samples required
- **Saturation:** Detected when actuator at bound + metric deficit persists
- **Oscillation:** 4+ directional reversals in 8 updates → DISABLED
- **Last-Known-Good:** Captured only in stable NORMAL (5+ updates)
- **Actuators:** jitter_sigma [jitter_floor, 0.20], switch_penalty [0.0, 0.30], consensus_blend [0.0, 0.15]

### Key ADR
- **0007:** Controller safety state machine

### Validation
- Deterministic tests: 40 scenarios (normal startup, hysteresis, saturation, rollback, recovery, oscillation, LKG promotion)
- Randomized invariant tests: state enum validity, actuator bounds, transition validity

---

## Stage 5 — Policy Lifecycle & Persistence

### Goal
Separate TRAIN/ADAPT/EVALUATE modes and add deterministic policy save/load.

### Implementation
- **Three modes:** TRAIN (exploration + updates), ADAPT (bounded low-rate updates), EVALUATE (frozen)
- **Policy format:** Binary with magic (0x504f4c59), version, schema, state/action counts, Q-table, SHA-256
- **Atomic save:** Temp file + validate + rename
- **Load validation:** Magic, version, schema, dimensions, finite values, digest, trailing bytes

### Controller-State Gating Matrix

| Mode | NORMAL | DEGRADED | SATURATED | ROLLBACK | RECOVERY | DISABLED |
|------|--------|----------|-----------|----------|----------|----------|
| TRAIN | updates | updates | suppressed | suppressed | suppressed | suppressed |
| ADAPT | updates | suppressed | suppressed | suppressed | suppressed | suppressed |
| EVALUATE | suppressed | suppressed | suppressed | suppressed | suppressed | suppressed |

### Key ADR
- **0008:** Policy lifecycle and persistence

### Validation
- 40 deterministic tests: TRAIN updates, ADAPT bounds, EVALUATE freeze, round-trip, corruption rejection
- Non-finite rejection, trailing bytes, wrong magic, digest mismatch

---

## Stage 6 — sched_ext MVP

### Goal
Boot a sched_ext-capable kernel in VirtualBox, load a minimal ORCHESTRA scheduler.

### Implementation
- **BPF program:** `orchestra_scx.bpf.c` (RUN + YIELD only)
- **System:** Fedora 40, kernel 6.12.15-100.fc40 (CONFIG_SCHED_CLASS_EXT=y)
- **Dispatch:** SCX_DSQ_LOCAL (per-CPU)
- **Slices:** RUN=5ms, YIELD=1ms
- **Partial switching:** SCX_OPS_SWITCH_PARTIAL

### Key ADR
- **0009:** sched_ext VirtualBox MVP

### Validation
- BPF verifier: passed on GitHub Actions CI
- struct_ops: registered successfully (map id, link id)
- State: enabled (partial) → disabled (unregistered)
- 5 load/unload cycles: no errors
- scx_simple gate: 3 cycles pass

---

## Stage 6B — Runtime Validation

### Goal
Prove scheduler correctness on live kernel in VirtualBox.

### Milestones
- Disk expanded: 15 GB → 64 GB
- Fedora 6.12.15 kernel validated as compatible environment
- scx_simple 3-cycle: PASS
- ORCHESTRA attach: state=enabled

### Resolution
- DSQ error: Fixed by removing `scx_bpf_consume` from dispatch callback
- kfunc mask error: Removed `scx_bpf_consume` from update_idle callback
- SWITCH_PARTIAL flag added

---

## Stage 7 — Signal Bridge

### Goal
Create userspace-to-BPF directive publication with generation safety.

### Implementation
- **Bridge contract:** `orchestra_bridge_v1.h` (packed structs, deterministic sizes)
- **Two-slot publication:** Userspace writes inactive slot → read-back → publish generation
- **Task identity:** TGID + PID + start_boottime cookie
- **5 actions:** RUN, YIELD, MIGRATE, THROTTLE, SLEEP in BPF enqueue
- **Adaptive slice:** 0.5ms–100ms bounded
- **Telemetry v2:** 40 counters (12 Stage 6 + 28 Stage 7)

### Controller-State Action Gating

| State | RUN | YIELD | MIGRATE | THROTTLE | SLEEP |
|-------|-----|-------|---------|----------|-------|
| NORMAL | allow | allow | allow | allow | allow |
| DEGRADED | allow | allow | reject | allow | reject |
| SATURATED | allow | fallback | reject | reject | reject |
| ROLLBACK | LKG/RUN | reject | reject | reject | reject |
| RECOVERY | allow | allow | reject | reject | reject |
| DISABLED | RUN only | reject | reject | reject | reject |

### Key ADR
- **0010:** Userspace-to-BPF signal bridge

### Validation
- Publication: gen 1→6, slots alternate 0↔1
- Invalid PID: exit 6
- Invalid CPU: published with BPF fallback
- 5-min stability: state=enabled throughout

---

## Stage 8 — Full Kernel Validation

### Goal
Exact same-revision kernel environment: source, BTF, headers, scheduler.

### Implementation
- **Kernel build:** x86_64_defconfig + SCHED_CLASS_EXT + DEBUG_INFO_BTF + XFS + E1000 + SATA_AHCI
- **Root cause of boot failure:** BLS entry path `linux /vmlinuz-6.12.96` → `linux /boot/vmlinuz-6.12.96`
- **Root cause of missing sched_ext:** `x86_64_defconfig` sets `CONFIG_DEBUG_INFO_NONE=y` which drops BTF and sched_ext

### Validation
- scx_simple 3-cycle: PASS (Fedora package)
- ORCHESTRA: loads, enables, publishes, unloads cleanly
- Multi-core: 1/2/4 workers all pass
- 5-min stability: state=enabled throughout
- Fault injection: invalid PID (exit 6), invalid CPU (fallback)
- Security: 10/10 hardening items complete

### Key ADR
- **0011:** Stage 8 full kernel validation

---

## Stage 9 — Production Benchmarking

### Goal
Compare ORCHESTRA scheduling overhead against Linux CFS baseline.

### Implementation
- **Harness:** `benchmarks/stage9/benchmark_compare.sh`
- **Workload:** 4 CPU-bound workers × 3 seconds each

### Results

| Scheduler | Time (ms) | Overhead |
|-----------|-----------|----------|
| Linux CFS | 2419 | baseline |
| ORCHESTRA | 2898 | +19.8% |

### Overhead Analysis
The ~20% overhead comes from:
1. BPF struct_ops callbacks per scheduling event
2. Bridge map lookups (4 maps × per-enqueue)
3. Task identity validation
4. Controller-state gating check
5. Telemetry counter increments (40+ atomic ops)

### Key ADR
- **0012:** Stage 9 production validation
