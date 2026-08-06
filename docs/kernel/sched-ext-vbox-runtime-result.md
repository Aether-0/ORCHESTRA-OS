
## Stage 6B Runtime Validation Results — 2026-08-06

### Aligned Environment
| Component | Version |
|-----------|---------|
| Guest OS | Fedora 40 |
| Running kernel | 6.12.15-100.fc40.x86_64 |
| Kernel source | v6.12.96 (stable) — `tools/sched_ext/` headers |
| BPF build target | v6.12.96 headers + running-kernel BTF |
| scx_simple | Fedora package `scx_c_schedulers-0.1.8-1.fc40` |
| ORCHESTRA commit | `23ae89c` |
| Branch | `integration/sched-ext-vbox-mvp` |

### Gate Results
| Gate | Status |
|------|--------|
| Stock kernel sched_ext support | PASS |
| scx_simple 3-cycle | PASS |
| ORCHESTRA BPF compile (v6.12.96 headers) | PASS |
| ORCHESTRA BPF verifier | PASS |
| ORCHESTRA struct_ops attach | PASS |
| ORCHESTRA sched_ext enabled (partial) | PASS |
| 5 ORCHESTRA load/unload cycles | PASS |
| Clean disable (unregistered from user space) | PASS |
| No DSQ errors | PASS |
| No panics/stalls | PASS |
| Userspace regression (25/34/5) | PASS |

### ORCHESTRA BPF Object
- Hash: `a9d4cee9f9e13641d0de1814b0870357e3743167b438b9fb3950847bf4787bfc`
- Flags: `SCX_OPS_SWITCH_PARTIAL`
- DSQ: `SCX_DSQ_LOCAL` (per-CPU)

### Known Limitations
- scx_simple from v6.12.96 source hits clang 18.1.8 BPF atomic bug; Fedora-packaged binary works
- Dispatch callback is minimal (telemetry-only); real action dispatch deferred to Stage 7
- No RUN/YIELD differentiation at kernel level yet
- No userspace-to-BPF signal bridge
