# 14. Benchmark Results

## Test Configuration
- **Environment:** Fedora 40 guest, 4 vCPU, 8 GB RAM, VirtualBox
- **Kernel:** Linux 6.12.96 (Stage 8 exact build)
- **ORCHESTRA commit:** `0ab5d7a`
- **Workload:** 4 CPU-bound workers × 3 seconds each, pinned to separate CPUs

## CPU-Bound Comparison

| Scheduler | Time (ms) | Relative |
|-----------|-----------|----------|
| Linux CFS | 2419 | 1.00× |
| ORCHESTRA | 2898 | 1.20× |

## Overhead Sources

ORCHESTRA's ~20% scheduling overhead is attributable to:

1. **BPF struct_ops callbacks** (~10 ops invoked per scheduling event)
2. **Bridge map lookups** (control + directive + task_state + telemetry per enqueue)
3. **Task identity validation** (TGID read, PID read, cookie comparison, expiry check)
4. **Controller-state gating** (6-case switch per action)
5. **Adaptive slice clamping** (bounds check, arithmetic)
6. **Telemetry increments** (40+ atomic fetch-and-add operations)
7. **Bridge CLI overhead** (userspace map write + read-back + generation publish)

## Limitations

- VirtualBox VM — not bare metal
- Single measurement per scheduler (no statistical significance)
- 4 vCPU maximum
- scx_simple source comparison excluded (clang 18.1.8 BPF atomic bug)
- Not a performance claim — research overhead measurement

## Benchmark Harness

```bash
bash benchmarks/stage9/benchmark_compare.sh
# Outputs: $HOME/stage9-benchmarks-<timestamp>/results.{csv,json}
```

## Multi-Core Throughput (Stage 8)

| Workers | State | Result |
|---------|-------|--------|
| 1 | enabled | gen published, clean |
| 2 | enabled | gen published, clean |
| 4 | enabled | gen published, clean |

All workers completed without errors. No scheduler stall or stranded task at any worker count.
