# 18. Appendix

## ADR Index

| ADR | Title |
|-----|-------|
| 0001 | Userspace state, metric, and controller contract |
| 0002 | Userspace signal-frame contract |
| 0003 | Metrics v3 conditioned coherence |
| 0004 | Effective userspace action metrics |
| 0005 | Burst-sensitive temporal stability |
| 0006 | Generation-stamped signal publication |
| 0007 | Controller safety state machine |
| 0008 | Policy lifecycle and persistence |
| 0009 | sched_ext VirtualBox MVP |
| 0010 | Userspace-to-BPF signal bridge |
| 0011 | Stage 8 full kernel validation |
| 0012 | Stage 9 production validation |

## Key Hashes

| File | SHA-256 |
|------|---------|
| orchestra_paper_cpu.c | `5fc21224846a2a17db0f02ce02efe8ebbe1067e40b0ad78e82419839d73657b9` |
| orchestra_paper_cpu (binary) | `3a68b633e29e9d91060fa9bba0305940f02d04678573da115796f23850383e03` |
| orchestra_bridge_v1.h | `08eaa93725f98331edffa67d3255b25bebcb589e8299401c40a089dc70007c97` |
| bzImage (v6.12.96) | `d3d50d26b3d1a91196318a2c99d1c71a859c3171b69276bd26414ae6dfa9e912` |
| BTF (v6.12.96) | `7af6be54b981c04e7e57c2043f3cb0247e05e564ff65271138197fd8a91ca458` |

## Repository Statistics

| Metric | Value |
|--------|-------|
| Total commits | ~62 |
| Total files | ~168 |
| Lines of C | ~4300 |
| Lines of Python | ~3400 |
| Lines of Markdown | ~8000 |
| ADRs | 12 |
| Test cases | 85 |
| Branches | 10+ |
| Contributors | 1 |

## Glossary

| Term | Definition |
|------|-----------|
| ARF | Adaptive Response Function — per-process action policy |
| BPF | Berkeley Packet Filter — kernel VM for safe programs |
| BTF | BPF Type Format — kernel type information for CO-RE |
| CFS | Completely Fair Scheduler — Linux default |
| CO-RE | Compile Once, Run Everywhere — BPF portability |
| DSQ | Dispatch Queue — sched_ext task queue |
| EEVDF | Earliest Eligible Virtual Deadline First |
| HMAC | Hash-based Message Authentication Code |
| LKG | Last Known Good — safe actuator snapshot |
| SCX | sched_ext — extensible scheduling class |
| Q | Coordination Index — geometric mean of S1-S4 |
