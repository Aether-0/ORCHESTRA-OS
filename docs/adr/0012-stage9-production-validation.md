# Stage 9 — Production-Quality Evaluation and Benchmarking

Status: **In Progress**

## Scope

Stage 9 evaluates the complete ORCHESTRA scheduling stack under controlled, reproducible conditions. No new features. No ABI changes.

## Workstreams

| WS | Description |
|----|-------------|
| 9A | Performance benchmark suite (CFS vs scx_simple vs ORCHESTRA) |
| 9B | Real hardware validation |
| 9C | Scalability (1-32 workers) |
| 9D | Stress testing (CPU, I/O, mixed, memory pressure) |
| 9E | Automated regression pipeline |
| 9F | Research artifacts (CSV, JSON, Markdown reports) |
| 9G | Documentation |

## Benchmark Metrics

Every benchmark records:
- Throughput (tasks/sec or ops/sec)
- Latency (mean, median, P95, P99)
- CPU utilization
- Context switches (voluntary + involuntary)
- Migration count
- Fairness (Jain index or completion-time variance)
- Scheduler overhead (dispatch count, BPF callback count)
- Bridge overhead (publication latency)
- Controller overhead

## Environment

Every run records:
- Host/guest hardware (CPU model, cores, RAM, disk)
- OS release
- Kernel release + SHA
- ORCHESTRA commit
- BPF object SHA-256
- Bridge binary SHA-256
- Compiler versions
- Timestamps

## Non-Goals

- Performance tuning
- Architecture redesign
- ABI or schema changes
- Fabricated numbers
