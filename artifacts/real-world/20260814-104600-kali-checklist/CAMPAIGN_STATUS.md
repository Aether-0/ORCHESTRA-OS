# Campaign status — consolidated checklist closeout

Campaign ID: `20260814-104600-kali-checklist`  
Consolidates: `20260814-093036-kali`, `20260814-095200-kali-auth`, `20260814-102000-kali-7port`, `20260814-103600-kali-actions`  
Date: 2026-08-14  
Host: kali (HP Pro Tower 280 G9)  
Kernel: 7.0.12+kali-amd64  
sched_ext at close: **disabled**  
bpffs: empty (`/sys/fs/bpf` only)  
Package temp at close: ~47°C  
Decision: **PARTIALLY_VALIDATED**

This campaign followed AGENTS.md INSPECT → BASELINE → BUILD → VERIFY → RUN → OBSERVE → REPEAT → DIAGNOSE → REPORT → ADVISE.

IMPLEMENTATION MODIFIED: **YES** (operator-authorized): Linux 7.0 sched_ext kfunc wrappers + DSQ enum restore in `orchestra_scx_stage7.bpf.c`; `ORCHESTRA_SCX_API_VERSION=70012`; bridge `--status` extra counters. No action/policy/reward/Q algorithm changes. No failing tests disabled.

Final remaining runtime this session:
- 3× load/unload cycles: PASS
- CLI / invalid PID / invalid CPU / stale SLEEP: PASS as input validation
- Unload while a worker existed: PASS (disabled; worker exited 0)
- `sudo chrt -f 20` under loaded ORCHESTRA: process remained SCHED_FIFO; scheduler stayed enabled until clean unload

Not run (safety / missing infrastructure):
- `stress_suite.sh orchestra` at 24-way (thermal: CFS 60s already ~79°C vs high=80°C)
- 10+ minute loaded stability
- `scx_simple` comparison
- network suite
- destructive `rm -rf /sys/fs/bpf/*` scripts
- in-tree 6.12.96 VBox bzImage (no NVMe)
