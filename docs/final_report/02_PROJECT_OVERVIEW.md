# 2. Project Overview

## Motivation

Linux scheduling has historically been reactive: CFS and EEVDF respond to observed load states. ORCHESTRA-OS introduces **predictive signal coordination** — a model where authenticated scheduling directives propagate from a global controller to individual processes through cryptographic signal frames.

## Research Program

The project progressed through nine stages of increasing complexity:

| Stage | Focus | Key Achievement |
|-------|-------|-----------------|
| 1 | Userspace Core | HMAC-SHA256 signal bus, 5-action RL |
| 2 | Metrics | v2→v6 append-only schemas |
| 3 | Signal Bus | C11 atomic two-slot publication |
| 4 | Controller | 6-state safety machine |
| 5 | Policy | TRAIN/ADAPT/EVALUATE lifecycle |
| 6 | sched_ext | Minimal BPF scheduler on VirtualBox |
| 6B | Runtime | scx_simple gate, ORCHESTRA enables |
| 7 | Bridge | Two-slot directive publication |
| 8 | Validation | Exact v6.12.96 kernel boot |
| 9 | Benchmark | CFS vs ORCHESTRA comparison |

## Repository Structure

```
ORCHESTRA-OS/
├── orchestra_paper_cpu_demo/    Userspace prototype
├── kernel/sched_ext/            BPF scheduler + bridge
├── benchmarks/                  Stage 8+9 harnesses
├── experiments/                 Manifests, schemas
├── tests/                       25 unit, 34 validator, 5 integration
├── docs/                        12 ADRs, architecture, kernel, security
├── tools/                       Benchmark runner, reporting
└── artifacts/                    Test results, kernel images
```

## Key Technologies

- **C11 atomics** for generation-stamped signal publication
- **BPF CO-RE** for portable kernel scheduling
- **HMAC-SHA256** for signal frame integrity
- **sched_ext** for Linux kernel scheduler extension
- **libbpf** for BPF program loading
- **Q-learning** with difference rewards for multi-agent coordination
