Campaign ID: 20260814-104600-kali-checklist (consolidates 093036, 095200-auth, 102000-7port, 103600-actions)
Date: 2026-08-14
Host: kali (HP Pro Tower 280 G9, i7-13700, 24 logical CPUs, 1 NUMA node, 15 GiB)
ORCHESTRA revision: unpacked tree `/home/sharda/Downloads/ORCHESTRA-OS-main` (not a git repository)
Kernel: 7.0.12+kali-amd64
sched_ext: enabled under orchestra_scx_stage7 during kernel phases; **disabled** at close
Overall result: **PARTIALLY_VALIDATED**

Checklist (98 rows):
- Applicable: 95
- PASS: 58
- FAIL: 3
- BLOCKED: 24
- INCONCLUSIVE: 10
- N/A: 3

Critical findings: none

High findings:
- F6 (historical): unmodified 6.12 BPF cannot load on 7.0 (`scx_bpf_dispatch` absent). Mitigated later by authorized 7.0 port.
- F7: first 7.0 attach without DSQ enum restore aborted (`non-existent DSQ 0x0`). Mitigated; later loads stayed enabled.
- F8: published canonical actions are stored but not shown effective (MIGRATE CPU unchanged; SLEEP accept/defer 0). Identity/snapshot match likely.

Validated on this machine:
- Userspace `make clean && make && make test` (30/30 named units × 4 compiler passes)
- Userspace paper-cpu Q/S1–S4 and tamper rejection (USERSPACE_VALIDATED only)
- Running kernel CONFIG_SCHED_CLASS_EXT, BTF, bpftool, libbpf, clang/gcc
- CFS CPU 1/2/4/8 and mixed; CFS stress 10s and 30s after `stress` installed
- 7.0-ported BPF load/unload; 3/3 load cycles; full-switch enqueue/running; clean unregister
- Bridge CLI rejects missing maps, unknown action, missing PID, invalid PID, invalid CPU, stale SLEEP not-before
- Unload while a userspace worker was alive
- SCHED_FIFO process existed while ORCHESTRA was loaded (policy remained FIFO)

Not validated:
- Effective kernel RUN/YIELD/MIGRATE/THROTTLE/SLEEP on a targeted task
- Isolated opt-in ownership (full switch_all=1 owns the whole machine)
- Kernel HMAC Signal Bus, predictor, S1–S4/Q, feedback controller, Hybrid Safety Layer
- ORCHESTRA vs CFS vs scx_simple with matched protocol and N≥5
- Orchestra-mode 24-way stress; 10+ minute loaded run; NUMA-aware WP8; cluster scale
- Deployment readiness

Most important reason for current limitations:
- Kernel prototype on 7.0 attaches and runs in full-switch fallback, but directive matching at enqueue is not demonstrated; paper WP2–WP6 live in userspace, not in this BPF.

Recommended next action:
- Diagnose BPF `task_identity(p)` vs bridge map keys / coherent snapshot without changing action semantics; do not claim experimental kernel validation until accepted≈enqueue for a published TID and MIGRATE moves the task. Do not boot the in-tree 6.12.96 VBox bzImage (NVMe disabled).
