# Implementation matrix (this host, 2026-08-14)

| Component | Status | Evidence | Testable on this machine? |
|---|---|---|---|
| sched_ext scheduler (Stage 7 BPF) | KERNEL_PROTOTYPED in tree; not built here | orchestra_scx_stage7.bpf.c; compile failed | Not until bpftool + KSRC + headers |
| bridge | in tree; not linked | orchestra_bridge.c; -lbpf missing | No |
| RUN | userspace yes; kernel not loaded | unit tests; no struct_ops | Kernel: no |
| YIELD | same | same | Kernel: no |
| MIGRATE | same | same | Kernel: no |
| THROTTLE | same | same | Kernel: no |
| SLEEP | same | same | Kernel: no |
| Signal Bus | userspace HMAC+publication; kernel maps only | make test; current-state.md | Kernel crypto: no |
| integrity/freshness | userspace yes; kernel generation/expiry in maps if loaded | tamper CSV; no load | Kernel: no |
| predictor | userspace yes; kernel no | paper-cpu CSV | Kernel: no |
| S1/S2/S3/S4/Q | userspace yes; kernel no | last-row tables | Kernel: no |
| controller | userspace yes; kernel no | CSV columns | Kernel: no |
| RT bypass | not in kernel prototype | current-state.md | No (Hybrid Safety) |
| NUMA-aware | not implemented | single node anyway | N/A / not implemented |
| distributed tier | not implemented | single host | No |
