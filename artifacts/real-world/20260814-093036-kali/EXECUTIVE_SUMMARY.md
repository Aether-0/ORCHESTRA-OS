Campaign ID: 20260814-093036-kali  
Date: 2026-08-14  
Host: kali (HP Pro Tower 280 G9 E PCI Desktop PC)  
ORCHESTRA revision: not a git repository; tree `/home/sharda/Downloads/ORCHESTRA-OS-main`; userspace binary SHA-256 `eecd6c80a6c8470c3d8b759020b2e75213ed21a935cf4ce3d4dc0645184726b2`  
Kernel: Linux 7.0.12+kali-amd64 (Kali 2026.3)  
sched_ext: present, `disabled` for the entire campaign (`enable_seq=0`)  
Overall result: **BLOCKED_BY_ENVIRONMENT**

Checklist:
- Applicable: 88 (91 rows including 3 N/A)
- PASS: 37
- FAIL: 2
- BLOCKED: 49
- INCONCLUSIVE: 0 checklist rows (userspace Q stability tracked as finding F3 / test T12u)
- N/A: 3

Critical findings: none (no panic, lockup, data loss, or scheduler-state corruption).

High findings:
- F1: cannot build or load the sched_ext BPF prototype (missing bpftool, libbpf-dev, kernel source, vmlinux.h; running 7.0.12 vs source targeting 6.12).

Validated on this machine:
- Userspace `make clean && make && make test` (30/30 named unit tests on four compiler passes; 21 benchmark-validator + 4 microbenchmark-runner + 34 CSV validator tests; 5 integration scenarios).
- Kernel *configuration* for sched_ext/BTF/BPF JIT on the running Kali kernel.
- Linux/CFS CPU and mixed baselines (1/2/4 workers × 8s, N=3; 1/2/4/8 workers × 30s cpu+mixed).
- 24-way CPU spin 10s (stock suite) and 60s (CPU phase only).
- Userspace paper-cpu baseline/orchestra/tamper CSVs with S1–S4/Q columns (userspace only).
- Privileged SCHED_FIFO/SCHED_RR via `sudo chrt`.

Not validated:
- Loading ORCHESTRA sched_ext.
- Task ownership (SCHED_EXT opt-in).
- Kernel RUN/SLEEP/MIGRATE/THROTTLE/YIELD effectiveness.
- Kernel signal integrity, predictor, S1–S4/Q, controller, Hybrid Safety Layer.
- scx_simple comparison.
- ORCHESTRA vs CFS performance with proven ownership.
- Network suite, NUMA-aware scheduling, long-duration loaded scheduler, cluster scale.
- Stock memory/I/O stress_suite completion.

Most important reason for current limitations:
- The running kernel exposes sched_ext, but this host cannot compile or load the Stage-7 BPF scheduler: no bpftool, no libbpf development package, no v6.12 kernel source / `scx/common.bpf.h`, no generated `vmlinux.h`, and a 7.0.12 vs 6.12 API gap.

Recommended next action:
- Authorize installing `bpftool`, `libbpf-dev`, `libelf-dev` (and optionally `linux-cpupower`, `numactl`, `stress`, `scx` schedulers). Provide a kernel source/headers tree matching the *intended* sched_ext ABI. Prefer booting the project’s validated 6.12.x kernel rather than a silent 7.0 port. Then rebuild BPF/bridge, load, prove ownership, and resume kernel checklist items. Do not treat this campaign as physical KERNEL_PROTOTYPED evidence.
