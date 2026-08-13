# 15. Limitations

## Hardware
- **NUMA:** Single-node VM topology. Multi-node NUMA validation deferred to Stage 10.
- **CPU:** 4 vCPU maximum tested. 8+ worker scaling not yet measured.
- **Platform:** VirtualBox only. Bare-metal benchmarks not yet performed.
- **Architecture:** x86_64 only.

## Kernel
- **Build:** x86_64_defconfig + additions. Full Fedora driver set not included.
- **scx_simple from source:** Fails on clang 18.1.8 (BPF 32-bit atomic bug). Fedora package used.
- **Initramfs:** Must be regenerated for different hardware.

## Bridge
- **Map pinning:** `orchestra_bridge --pin-maps` pins the four bridge maps after struct_ops register. Harnesses must still call it after every load.
- **Privileges:** Bridge CLI requires CAP_BPF + CAP_SYS_ADMIN.
- **Map names:** Truncated to 15 characters by bpftool.

## Controller
- **Userspace-only:** Controller runs in userspace. BPF only enforces gating.
- **Recovery:** Uses rolling window hysteresis; may be slow to detect drift.

## Actions
- **SLEEP:** Min-slice deferral until `not_before_ns`; not a kernel `TASK_INTERRUPTIBLE` sleep. Custom-DSQ hold was not used because `scx_bpf_consume` previously failed on this 6.12 path.
- **MIGRATE:** Dispatches to `SCX_DSQ_LOCAL_ON | target_cpu` and kicks that CPU. Effectiveness still needs ownership-proven traces (running CPU of the opted-in task).
- **THROTTLE:** Min slice (`BRIDGE_SLICE_MIN_NS`); not precise bandwidth control.
- **Partial switch:** `SCX_OPS_SWITCH_PARTIAL` is retained. Benchmarks must `sched_setattr(SCHED_EXT)` (`orchestra_bridge --opt-in`) or enqueue/run stay 0.

## Security
- **Authentication:** Bridge maps have no cryptographic authentication (local trust only).
- **Policy digest:** SHA-256 for corruption detection, not authentication.
- **Privilege drop:** No privilege drop after scheduler attach.

## Research Status
- ORCHESTRA is a **research prototype**, not production software.
- No performance claims without controlled statistical evidence.
- No hard real-time guarantees.
- No production security certification.
- No formal verification.
