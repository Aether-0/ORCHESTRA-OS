# ORCHESTRA-OS Kali build-preparation campaign

- Campaign: 20260821-124731-redshadow-kali-build-prep
- Host: redshadow
- Time window: 2026-08-21, Asia/Kolkata
- Repository commit: 68295dc134774c7699764b3234e40ac7c764cc5c
- Branch: main
- Overall status: READY_FOR_NEXT_REAL_MACHINE_WITH_TARGET_SIDE_BLOCKERS

This campaign prepared the existing ORCHESTRA-OS tree for the next controlled
Kali real-machine session. It did not load sched_ext, attach a BPF program, run
the benchmark/stress suites, or modify source, tests, scripts, kernel
configuration, package state, or persistent system configuration.

Completed:

- Kali capability checks passed: sched_ext, BPF/JIT, BTF, and required kernel
  configuration are present.
- Userspace build and regression evidence was captured.
- The running-kernel BTF header was generated outside the source tree.
- Existing bridge, loader, and fixed-work workload binaries were built outside
  the source tree.
- A complete next-session handoff is available in
  ../20260821-021012-redshadow-kali-handoff/KALI_HANDOFF.md.

Not complete:

- No BPF scheduler object was produced. The available full kernel source is
  Linux 7.2.0-rc6, while this host runs Kali Linux 7.0.12+kali-amd64. The
  repository targets ORCHESTRA_SCX_API_VERSION=70012. Building against the
  mismatched source would not be valid runtime evidence.
- Runtime load/ownership/action/unload testing was not run. The current user
  could not obtain non-interactive sudo, and this host is only the build-prep
  context.
- libbpf/libelf development headers/pkg-config metadata are absent. Runtime
  shared libraries exist, so the loader was built using existing kernel-tree
  headers and direct runtime-library paths as a preparation artifact; rebuild
  it on the target with target-matched development inputs.
- Optional tools missing on this host: llvm-config, numactl, sensors, perf, and
  stress. These block only the corresponding optional phases.

The next physical target must provide:

1. A root-capable, disposable/recoverable test machine.
2. A full kernel source tree matching its running uname -r and containing
   tools/sched_ext/include/scx/common.bpf.h.
3. libbpf/libelf development headers and link inputs, or an explicitly
   verified equivalent.
4. A fresh target-BTF-generated vmlinux.h and target-built
   orchestra_scx_stage7.bpf.o.
5. Pre-load BPF inventory and the safe loader-only attach/unload protocol.
6. Per-TID ownership telemetry before any performance or comparison claim.

No deployment-readiness claim is made.
