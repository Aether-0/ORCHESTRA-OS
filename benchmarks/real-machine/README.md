# ORCHESTRA-OS Real-Machine Benchmarks

## Quick Start

```bash
# 1. Check your machine
bash sanity_check.sh

# 2. Run stress tests (60 seconds)
bash stress_suite.sh 60 cfs     # CFS baseline
bash stress_suite.sh 60 orchestra  # ORCHESTRA (load scheduler first)

# 3. Run benchmarks (CFS vs scx_simple vs ORCHESTRA)
bash benchmark_suite.sh
```

## Scripts

| Script | Purpose |
|--------|---------|
| `sanity_check.sh` | Check kernel, tools, sched_ext readiness |
| `stress_suite.sh` | CPU, memory, I/O, mixed workload stress |
| `benchmark_suite.sh` | CFS vs scx_simple vs ORCHESTRA comparison |

## Stress Tests

```
CPU stress     → N workers × 100% CPU spin loop
Memory stress  → 50% RAM allocation + pressure
I/O stress     → Parallel read/write operations
Mixed workload → CPU + I/O combined
Health check   → Kernel log scan for panics/stalls
```

## Benchmark Workloads

- 1 worker  × 30 seconds
- 2 workers × 30 seconds
- 4 workers × 30 seconds
- 8 workers × 30 seconds

Compared across CFS, scx_simple, ORCHESTRA.

## Output

All results in `/tmp/orchestra-bench-<timestamp>/results.csv` and `/tmp/orchestra-stress-<timestamp>/results.csv`.
