# Stage 9 — Benchmark Methodology

## Test Configuration
- Guest: Fedora 40, 4 vCPU, 8 GB RAM, 64 GB disk
- Kernel: Linux 6.12.96 (Stage 8 exact build)
- Scheduler versions: CFS (kernel default), scx_simple (Fedora 0.1.8), ORCHESTRA (Stage 7 BPF)

## Workload
- 4 CPU-bound workers × 3 seconds each
- Each worker: tight spin loop (`while [ $(date +%s) -lt $e ]; do :; done`)
- Pinned to separate CPUs via `taskset -c`

## Metrics
- Total wall-clock time for all workers to complete
- dispatch_count, run_count, yield_count, fallback_count, scheduler_error_count

## Results (2026-08-07)
| Scheduler | Time (ms) | Notes |
|-----------|-----------|-------|
| CFS | 2419 | Kernel default fair scheduler |
| ORCHESTRA | 2898 | +20% overhead, expected BPF & bridge cost |

## Limitations
- VirtualBox environment — not bare metal
- Single measurement — not statistically significant
- scx_simple comparison omitted (output volume issue)
- 4 vCPU limit
