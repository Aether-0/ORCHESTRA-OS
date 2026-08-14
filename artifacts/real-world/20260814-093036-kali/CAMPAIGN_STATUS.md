# Campaign Status

- Campaign ID: 20260814-093036-kali
- Started: 2026-08-14T09:30:36+01:00
- Ended: 2026-08-14T09:43:22+01:00 (final state capture)
- Host: kali
- Path: `/home/sharda/Downloads/ORCHESTRA-OS-main/artifacts/real-world/20260814-093036-kali`
- Decision: `BLOCKED_BY_ENVIRONMENT`
- Overall claim class on this host: `USERSPACE_VALIDATED` (userspace path); kernel runtime `NOT_VALIDATED` / blocked
- Implementation modified: NO
- Packages installed: NO
- Persistent sysctl/governor/kernel changes: NO
- Scheduler loaded: NO (`/sys/kernel/sched_ext/state=disabled`)

## Phase status

| Phase | Result |
|---|---|
| 0 Inventory | DONE |
| 1 Maturity audit | DONE |
| 2 Userspace build/test | PASS |
| 3 Sanity / kernel config | DONE (config PASS; bpftool missing) |
| 4 Linux baseline | DONE (CFS) |
| 5 BPF/bridge build | BLOCKED |
| 6 Load/unload | BLOCKED |
| 7 Ownership | BLOCKED |
| 8 Canonical kernel actions | BLOCKED |
| 9 Hybrid Safety / RT kernel | BLOCKED_NOT_IMPLEMENTED + no load |
| 10–13 Signal/predictor/Q/controller kernel | BLOCKED_NOT_IMPLEMENTED |
| 14 Instrumentation kernel | BLOCKED |
| 15 CFS benchmarks | PASS (ORCHESTRA skipped) |
| 16 Stress | CPU PASS; suite FAIL on memory tmpfs; orchestra BLOCKED |
| 17 Full compare | CFS PASS; scx/ORCHESTRA skipped |
| Remaining kernel checklist | BLOCKED |

## Safety notes

- Dual-boot disk present (Windows-sized NTFS-like partitions). I/O tests used `/tmp` only.
- 24-way CPU 60s: package temperature 79°C vs high 80°C / crit 100°C. Stopped further 24-way stress.
- `full_compare.sh` / `p0` / `stage8` destructive bpffs wipes were **not** executed (BPF file missing or script marked unsafe).
- Leftover `/tmp/orchestra-stress-{1,2}` (3.9G each) were deleted after the failed memory phase.
