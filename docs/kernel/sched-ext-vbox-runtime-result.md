
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

## Stage 7 Closeout — 2026-08-06

### Aligned Environment
| Component | Version | SHA-256 |
|-----------|---------|---------|
| Guest OS | Fedora 40 (Forty) | — |
| Running kernel | 6.12.15-100.fc40.x86_64 | — |
| Kernel source | Linux v6.12.96 (stable) | `ab871af8...` (BTF) |
| sched_ext headers | v6.12.96 tools/sched_ext/ | — |
| vmlinux.h | Generated from running kernel BTF | `f8633340...` |
| bridge_v1.h source | included | `08eaa937...` |
| stage7 BPF source | orchestra_scx_stage7.bpf.c | `a14b3a75...` |
| stage7 BPF object | orchestra_scx_stage7.bpf.o | `4fe66db1...` |
| bridge CLI | bridge/orchestra_bridge | `be31a86a...` |
| userspace source | orchestra_paper_cpu.c | `5fc21224...` |
| userspace binary | orchestra_paper_cpu | `3a68b633...` |

### Alignment Approach
Fedora 6.12.15 alignment with v6.12.96 sched_ext headers. The sched_ext BPF API is stable within 6.12.x series. Both scx_simple (Fedora-packaged, 6.14-built) and ORCHESTRA (6.12.96 headers) function correctly on the 6.12.15 kernel.

### Runtime Results
| Gate | Status | Detail |
|------|--------|--------|
| scx_simple 3-cycle | PASS | Clean enable/disable |
| Stage 7 BPF compile | PASS | 0 errors |
| Stage 7 BPF verifier | PASS | struct_ops accepted |
| struct_ops attach | PASS | id 505, link 116 |
| state enabled (partial) | PASS | dmesg confirms |
| Bridge status | PASS | magic=0x4f524342, fmt=1, schema=1 |
| Dry-run no-mutation | PASS | gen stays at 0 after dry-run |
| Two-slot publication | PASS | 6 gens, slots alternate 0↔1 |
| Task identity check | PASS | Invalid PID rejected (exit 6) |
| RUN | PASS | Published via bridge |
| dmesg enables | 20+ events | No errors |
| enable_seq | 50 | Cumulative |
| Userspace regression | PASS | 25/25, 34/34, 5/5 |
| Clang analyzer | PASS | 0 findings |

### Known Limitations
- SLEEP deferred eligibility not runtime-tested (capability pending)
- PID reuse protection uses start-time cookie; full CO-RE cookie pending
- Maps must be individually pinned after struct_ops registration
- Mixed kernel version (6.12.15 running, 6.12.96 headers)
