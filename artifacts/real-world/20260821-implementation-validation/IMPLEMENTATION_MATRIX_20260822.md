# ORCHESTRA-OS implementation maturity matrix — 2026-08-22

This additive matrix records the fixed-point signal bridge slice. It does not
replace earlier matrices or promote compile-only evidence to runtime evidence.

| Component | Status | Evidence | Testable on this machine? |
|---|---|---|---|
| sched_ext scheduler | KERNEL_PROTOTYPED | Exact 7.0.12 BPF build; runtime attach still privilege-blocked | Build yes; attach no |
| bridge | KERNEL_PROTOTYPED | Strict build, ABI/parser tests, exact map schema | Build/tests yes; map runtime no |
| Signal frame transport | KERNEL_PROTOTYPED | `orch_signal`, 152-byte fixed-point ABI, bridge readback and sequence/freshness checks | Attach-dependent |
| Required-signal gate | KERNEL_PROTOTYPED | BPF `signal_is_valid`, `BRIDGE_DIRECTIVE_F_REQUIRE_SIGNAL`, invalid/stale counters | Attach-dependent |
| Userspace-to-kernel signal stream | KERNEL_PROTOTYPED | 176-byte stream ABI; engine converts prediction/metrics and publishes before directives | Attach-dependent |
| RT directive admission guard | USERSPACE_VALIDATED / KERNEL_PROTOTYPED boundary | Bridge checks `sched_getscheduler` and rejects FIFO/RR/DEADLINE targets before publication | Userspace yes; kernel coexistence no |
| Kernel HMAC verification | NOT_IMPLEMENTED | BPF validates local map structure/coherence only; no HMAC key/tag in the kernel frame | No |
| Kernel predictor | NOT_IMPLEMENTED | No predictor state/update/output in BPF | No |
| Kernel S1/S2/S3/S4/Q computation | NOT_IMPLEMENTED | Values are transported from userspace; BPF does not calculate them | No |
| Kernel feedback controller | NOT_IMPLEMENTED | No controller update/actuator loop in BPF | No |
| RT/Hybrid Safety Layer | NOT_IMPLEMENTED | No complete kernel RT bypass/coexistence contract | No |
| NUMA-aware scheduling | NOT_IMPLEMENTED / N/A environment | No NUMA policy; host has one NUMA node | No |
| Distributed tier | NOT_IMPLEMENTED | No distributed implementation or peer test infrastructure | No |
