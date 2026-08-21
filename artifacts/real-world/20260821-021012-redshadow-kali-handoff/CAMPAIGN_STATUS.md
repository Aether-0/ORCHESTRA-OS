# Kali target readiness campaign

Campaign ID: 20260821-021012-redshadow-kali-handoff
Prepared: 2026-08-21
Repository revision: 68295dc134774c7699764b3234e40ac7c764cc5c
Preparation host: redshadow (not the target machine, by user instruction)

## Result

PREPARED_FOR_TARGET_PREFLIGHT

This is a preparation and handoff artifact, not a runtime campaign. No
sched_ext scheduler was loaded or unloaded, no reboot was attempted, no
packages were installed, and no ORCHESTRA source or test code was modified.
The target Kali machine still needs to pass the preflight and exact-kernel
build gates in KALI_HANDOFF.md.

The current claim remains KERNEL_PROTOTYPED, not EXPERIMENTALLY_VALIDATED or
DEPLOYMENT_READY. Prior physical-Kali evidence proved 7.0 attach, full-switch
activity, and clean unload, but did not prove effective per-task canonical
actions.

## Source/worktree handling

- Existing user changes were preserved; the worktree was not cleaned or reset.
- No implementation, test, benchmark, or repository script was edited.
- The handoff is stored under artifacts/real-world/ only.
- Existing untracked files and prior campaign evidence remain untouched.

## Target gate summary

| Gate | Current preparation state | Target evidence required |
|---|---|---|
| Target identity and recovery | Pending | Dedicated/disposable Kali host, fallback kernel/console, storage and thermal headroom |
| Kernel/API alignment | Defined | Running kernel and exact source/tool headers match the current 7.0.12 API target |
| Toolchain | Defined | clang, bpftool, libbpf-dev, libelf-dev, zlib1g-dev, make, gcc |
| Userspace regression | Not run on target | make clean, make, make check, make test with captured output |
| BPF/bridge build | Not run on target | Target-BTF-generated header and source/object/bridge/loader hashes |
| Safe load/unload | Not run on target | orchestra_loader, state disabled -> enabled -> disabled, owned pins only |
| Ownership | Pending | Non-opted task stays outside; one long-lived opted task reaches per-task enable/enqueue/running |
| Canonical actions | Pending | Requested/accepted/dispatched/effective evidence for the exact target TID |
| Performance/stress | Deferred | Only after ownership and thermal/storage gates pass |

## Prior evidence that must not be overclaimed

See artifacts/real-world/20260814-104600-kali-checklist/ and
output/doc/ORCHESTRA_Kali_Failure_Continuation_Report_2026-08-18.html.
Those artifacts classify the prior physical campaign as PARTIALLY_VALIDATED:
load/unload worked after the authorized 7.0 API port, while effective
MIGRATE/SLEEP and isolated per-task action ownership remained unproven.
