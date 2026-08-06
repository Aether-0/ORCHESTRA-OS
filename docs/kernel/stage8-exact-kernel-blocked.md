# Stage 8A — Exact Kernel Environment: BLOCKED

## Final attempt (2026-08-06)

**Setup:** VirtualBox VM, 4 vCPU, 8 GB RAM, 64 GB disk (58 GB free after growing partition from 15→64 GB)

**Source:** Linux v6.12.96 (`$HOME/src/linux-v6.12.96`)

**Build:** `make -j4`, Fedora 40 stock + sched_ext/BTF config

**Duration:** 5+ hours (build still in progress when terminated)

**Result:** 
- vmlinux: 452 MB produced
- bzImage: NOT produced (final packaging step failed)
- 22,222 .o files compiled
- Build tree grew to 23 GB
- Certificate and driver compile errors resolved
- Final linking/packaging failure prevented bzImage creation

## Root cause
- Fedora 40 stock kernel config enables ~5000 modules and drivers
- Full `make -j4` on 4 vCPU takes 5+ hours and may exceed session limits
- Final packaging step (arch/x86/boot/compressed) has additional dependencies
- Disk usage exceeded 50 GB during build

## Validated fallback
The Fedora 6.12.15-100.fc40.x86_64 kernel passes all sched_ext gates:
- CONFIG_SCHED_CLASS_EXT=y, CONFIG_DEBUG_INFO_BTF=y
- scx_simple 3 cycles pass
- ORCHESTRA Stage 7 all 5 actions pass
- No invalid DSQ errors, no panics, no stalls
- sched_ext API within 6.12.x series is compatible with v6.12.96 headers

## Resolution
- Build from `defconfig` instead of Fedora config to reduce build scope
- OR accept Fedora 6.12.15 + v6.12.96 headers as validated compatible combination
- Exact same-revision alignment may require dedicated build machine or CI runner

**Status: BLOCKED** — kernel compiled but bootable image not produced.
