# Authorized continuation campaign

- Campaign ID: 20260814-095200-kali-auth
- Continues: 20260814-093036-kali
- User authorized package install and remaining testing
- Implementation modified: **NO** (no ORCHESTRA source edits; no 7.0 API rename)

## Packages installed

- bpftool 7.7.0+7.0.12-2kali1
- libbpf-dev 1:1.7.0-1
- libelf-dev 0.195-1
- linux-headers-7.0.12+kali-amd64 + common
- linux-source-7.0
- linux-cpupower, numactl, stress

Not installed: new kernel, scx_simple (no package).

## Build

- Bridge: **PASS** (`kernel/sched_ext/bridge/orchestra_bridge`, SHA-256 `8299a5f18b086707e13cda3293d106741c02e37dd31cc6b95613e1ece27e8e7f`)
- Loader: **PASS**
- `vmlinux.h` from running 7.0 BTF: **PASS** (137726 lines)
- Stage-7 BPF vs **7.0** `common.bpf.h`: **FAIL** — undeclared `scx_bpf_dispatch` / `scx_bpf_dispatch_vtime` / `__COMPAT_scx_bpf_dispatch_from_dsq` (source forbids compile-only rename)
- Stage-7 BPF vs **v6.12.96** scx headers + 7.0 `vmlinux.h`: **PASS compile** (2 likely/unlikely warnings)
  - object SHA-256 `3ff5b8683ae8ed7819fd5763e4c7aca091d8b8bd460ed6020f0b2c2af69b5686`

## Load

```
sudo bpftool struct_ops register orchestra_scx_stage7.bpf.o /sys/fs/bpf/orch
```

- rc=255
- `libbpf: extern (func ksym) 'scx_bpf_dispatch': not found in kernel or module BTFs`
- `/sys/kernel/sched_ext/state` remained **disabled**
- Running kernel kfuncs include `scx_bpf_dsq_insert` / `scx_bpf_dsq_insert_vtime`, not `scx_bpf_dispatch`

This is the documented 6.12→later DSQ-insert rename. **IMPLEMENTATION CHANGE REQUIRED** (semantic review, not a mechanical rename). Not performed.

## Stress (CFS, after `stress` installed)

| duration | cpu | mem | io | mixed | health | rc |
|---|---|---|---|---|---|---|
| 10s | PASS | PASS | PASS | PASS | WARN | 0 |
| 30s | PASS | PASS | PASS | PASS | WARN | 0 |

Health WARN: script greps dmesg for `BUG`; pre-existing ACPI **BIOS Error** matches. Not a new panic.

60s full suite not started: package 77°C after 30s suite vs high 80°C.

Orchestra stress: not run (scheduler not loaded).

## Still blocked

- Ownership, kernel actions, kernel Q, RT hybrid, scx_simple comparison, ORCHESTRA vs CFS with ownership
- Kernel 7.0.12 needs an approved sched_ext API port of `orchestra_scx_stage7.bpf.c`

## Decision

Still **BLOCKED_BY_ENVIRONMENT** for kernel runtime, now with a precise first failure: **missing kfunc `scx_bpf_dispatch` on Linux 7.0.12**. Toolchain is no longer the blocker.
