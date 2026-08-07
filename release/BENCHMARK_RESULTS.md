# Benchmark Results

## Test Environment
- Guest: Fedora 40, 4 vCPU, 8 GB RAM
- Kernel: Linux 6.12.96 (Stage 8 exact build)
- ORCHESTRA commit: `0ab5d7a`

## CPU-Bound Workload (4 workers × 3 seconds each)

| Scheduler | Time (ms) | Overhead |
|-----------|-----------|----------|
| Linux CFS | 2419 | baseline |
| ORCHESTRA | 2898 | +19.8% |

## Methodology
- Workers: tight CPU spin loop pinned to separate cores
- CFS measured with no sched_ext scheduler loaded
- ORCHESTRA measured with Stage 7 scheduler active + bridge RUN published
- Single measurement per scheduler (research prototype — not production data)

## Overhead Sources
ORCHESTRA's ~20% overhead comes from:
1. BPF struct_ops callbacks (~10 ops × per-event)
2. Bridge control/directive map lookups (4 maps per enqueue)
3. Task identity validation (TGID + PID + cookie)
4. Controller-state gating check
5. Telemetry counter increments (40+ atomic operations)
6. Bridge CLI map write + read-back + publish

## Limitations
- VirtualBox VM — not bare metal
- Single measurement — no statistical significance
- scx_simple comparison excluded (clang 18.1.8 BPF atomic bug prevented source build)
- 4 vCPU maximum
- Not a performance claim — research prototype overhead measurement
