# ORCHESTRA-OS sched_ext Kernel Integration — Stage 6 MVP

**Status:** Implemented  
**Maturity:** Kernel-prototyped (VirtualBox)

## Scope

This directory implements a minimal sched_ext scheduler for the ORCHESTRA-OS
research program. Stage 6 provides:

- Partial opt-in via `SCHED_EXT` scheduling policy
- RUN action: bounded 5ms slice on global DSQ
- YIELD action: bounded 1ms slice with eventual progress
- Unknown action fallback to RUN
- Frozen deterministic policy (no online learning in kernel)
- Bounded dispatch loops (max 4 per tick)
- Per-task state tracking (action, fallback count)
- Global telemetry counters (load/unload/enable/enqueue/dispatch/run/yield/fallback/error)
- Safe unload — tasks return to Linux fair scheduler

## Files

| File | Purpose |
|------|---------|
| `include/orchestra_scx.h` | Shared definitions (actions, maps, telemetry) |
| `orchestra_scx.bpf.c` | BPF scheduler program |
| `orchestra_scx.c` | Userspace loader skeleton |
| `scripts/check_kernel_config.sh` | Kernel config validation |
| `scripts/verify_sched_ext.sh` | sched_ext subsystem verification |
| `tests/test_optin.c` | Partial opt-in test driver |
| `tests/test_dispatch.c` | Dispatch correctness exercises |

## Prerequisites

- Linux 6.12+ with `CONFIG_SCHED_CLASS_EXT=y`
- `CONFIG_DEBUG_INFO_BTF=y`
- clang/LLVM 15+ for BPF compilation
- bpftool, libbpf
- Root or `CAP_BPF`+`CAP_SYS_ADMIN` for scheduler load

## Build

```bash
# From the Linux kernel source tree:
cd $ORCHESTRA_KERNEL_SRC
make -C tools/bpf/bpftool

# Build the ORCHESTRA BPF scheduler:
clang -O2 -target bpf -g \
    -I $ORCHESTRA_KERNEL_SRC/tools/lib \
    -I $ORCHESTRA_OS/kernel/sched_ext/include \
    -c orchestra_scx.bpf.c -o orchestra_scx.bpf.o

# Verify with BPF verifier:
bpftool prog load orchestra_scx.bpf.o /sys/fs/bpf/orchestra_scx type sched_ext

# Generate skeleton:
bpftool gen skeleton orchestra_scx.bpf.o > orchestra_scx.skel.h

# Build userspace loader:
cc -O2 -Wall -Wextra -Werror orchestra_scx.c -o orchestra_scx -lbpf -lelf -lz
```

## Load and Test

```bash
# Run the loader (requires root):
sudo ./orchestra_scx

# Verify sched_ext is active:
cat /sys/kernel/sched_ext/state

# Should show "orchestra_scx_stage6" as the active scheduler
```

## Telemetry

After scheduler unload, telemetry is printed to stdout:

- `load_count` / `unload_count` — scheduler attach/detach events
- `task_enable_count` / `task_disable_count` — opt-in/opt-out events
- `enqueue_count` / `dispatch_count` — scheduling operations
- `run_count` / `yield_count` — action frequencies
- `fallback_count` / `invalid_action_count` — error diagnostics

## Unload

```bash
# Ctrl+C in the loader unloads the scheduler
# Or:
sudo bpftool struct_ops unregister /sys/fs/bpf/orchestra_scx/orchestra_sched_ops
```

All opted-in tasks return to CFS/EEVDF safely.

## Limitations (Stage 6)

- No SLEEP, MIGRATE, or THROTTLE kernel implementations
- No userspace-to-BPF signal bridge
- No online policy learning in kernel
- Fixed slice durations only
- Single frozen policy
- No NUMA-aware CPU selection
- Requires VirtualBox or test VM for safe evaluation
