Campaign ID: 20260814-095200-kali-auth (continuation of 20260814-093036-kali)  
Date: 2026-08-14  
Host: kali  
ORCHESTRA revision: same unpacked tree; BPF object SHA-256 `3ff5b8683ae8ed7819fd5763e4c7aca091d8b8bd460ed6020f0b2c2af69b5686`  
Kernel: 7.0.12+kali-amd64  
sched_ext: disabled after failed register  
Overall result: **BLOCKED_BY_ENVIRONMENT** (kernel API mismatch; toolchain now present)

Checklist delta vs prior campaign:
- Tooling gaps for bpftool/libbpf-dev: resolved
- Bridge link: now PASS
- BPF compile against 6.12 headers: PASS
- BPF load: FAIL (scx_bpf_dispatch absent)
- CFS stress 10s/30s with `stress`: PASS (health WARN = ACPI false positive)
- Kernel ownership/actions: still not executed

Critical findings: none  

High findings:
- Load fails: kernel BTF has `scx_bpf_dsq_insert*`, object requires `scx_bpf_dispatch`. Source comments forbid a compile-only rename.

Validated on this machine (this continuation):
- Authorized install of bpftool, libbpf-dev, headers, linux-source, stress, numactl, cpupower
- Bridge and loader binaries
- vmlinux.h from running BTF
- BPF object built from unmodified Stage-7 C using v6.12.96 scx headers
- CFS stress 10s and 30s CPU/memory/I/O/mixed

Not validated:
- Any ORCHESTRA-owned scheduling on this kernel

Most important reason for current limitations:
- Running Linux 7.0.12 renamed the 6.12 `scx_bpf_dispatch*` kfuncs to `scx_bpf_dsq_insert*`. Unmodified Stage-7 BPF cannot attach.

Recommended next action:
- Boot the project’s validated 6.12.x sched_ext kernel, **or** perform a reviewed (not mechanical) port of `orchestra_scx_stage7.bpf.c` wrappers to the 7.0 insert/move API, then rebuild, load, and prove ownership. Do not treat the compiled-but-unloaded object as a kernel runtime result.
