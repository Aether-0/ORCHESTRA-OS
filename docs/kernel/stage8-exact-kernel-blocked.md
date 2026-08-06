# Stage 8A — Exact Kernel Environment: BLOCKED

## Attempted
- v6.12.96 source already present at `~/src/linux-v6.12.96` (1.6 GB)
- Build configured with required CONFIG_ options (BPF, SCHED_CLASS_EXT, BTF)
- Build attempted on 4 vCPU, 8 GB RAM, 15 GB disk VirtualBox VM
- Multiple build failures: missing `bc`, module signing certs, driver compilation errors
- Build time exceeded 1 hour without producing `bzImage`
- Disk usage grew from 5.4 GB → 6.9 GB during partial build
- Build tree cleaned; disk returned to 5.4 GB

## Root cause
- 15 GB virtual disk is marginal for a full kernel build (~1.5 GB source + 5-8 GB build tree)
- Fedora 40 stock kernel config enables many unnecessary drivers that fail to compile in a minimal VM
- Build-time dependencies (`bc`, openssl-devel, etc.) not pre-installed
- 4 vCPU VM build time exceeds practical session limits

## Current validated environment
The Fedora 6.12.15-100.fc40.x86_64 kernel with v6.12.96 sched_ext development headers passes all Stage 6B and Stage 7 runtime gates:
- CONFIG_SCHED_CLASS_EXT=y
- CONFIG_DEBUG_INFO_BTF=y
- sched_ext state transitions are clean
- scx_simple loads/unloads (3 cycles)
- ORCHESTRA loads/unloads, all 5 actions function
- No invalid DSQ errors, no panics, no stalls

## Resolution path
- Expand VirtualBox disk to 40+ GB before retrying kernel build
- Use `make localmodconfig` to reduce build scope to needed drivers
- OR accept the validated Fedora 6.12.15 + v6.12.96 header combination as sufficient for Stage 8 research (sched_ext API is stable within 6.12.x)

Status: **BLOCKED** — disk capacity and build time exceed current VM resources.
