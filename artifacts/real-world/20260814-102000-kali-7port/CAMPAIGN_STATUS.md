# 7.0 wrapper port — attach evidence

Date: 2026-08-14T10:26
Host: kali 7.0.12+kali-amd64
Implementation: wrapper + enum restore in `orchestra_scx_stage7.bpf.c`; `ORCHESTRA_SCX_API_VERSION=70012`.

## Why not boot 6.12.96 artifact kernel

`artifacts/kernel-v6.12.96-orchestra-stage8.bzImage` has `# CONFIG_BLK_DEV_NVME is not set`. This HP boots from NVMe. Installing that kernel would not boot.

## What changed

- `scx_bpf_dispatch` → `scx_bpf_dsq_insert`
- `scx_bpf_dispatch_vtime` → `scx_bpf_dsq_insert_vtime`
- `__COMPAT_scx_bpf_dispatch_from_dsq` → `scx_bpf_dsq_move`
- `#undef` of zeroed `enums.autogen.bpf.h` DSQ/kick/enq macros so vmlinux enum values are used (generic libbpf loader does not inject SCX_OPS_LOAD volatiles)
- First attach without that undef: enabled then **runtime error** `non-existent DSQ 0x0 for ksoftirqd/22`

## Load/unload

- `sudo orchestra_loader --load orchestra_scx_stage7.bpf.o`
- `/sys/kernel/sched_ext/state=enabled`, `switch_all=1`
- dmesg: `BPF scheduler "orchestra_scx_stage7" enabled`
- `--status`: `scheduler: orchestra_scx_stage7` `scx_api=70012`
- `sudo orchestra_loader --unload` → `disabled (unregistered from user space)`

## Ownership / actions (exploratory, n=1)

- Full switch: all tasks take the ORCHESTRA path (`running` already ~97k before explicit opt-in).
- `--opt-in` admitted TID; `--publish RUN` generation=1, accepted/dispatched increased 0→11.
- High `fallback` (~104k vs running ~104k): many tasks had no directive (expected without per-task RUN).
- MIGRATE worker exited before inspect; **effective CPU movement not proven**.
- No `--inspect` CLI.

Claim class: **KERNEL_PROTOTYPED on this physical host** for load/unload + full-switch enqueue/running. Not experimental validation of MIGRATE/SLEEP/THROTTLE/YIELD effectiveness.
