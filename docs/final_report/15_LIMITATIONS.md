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
- **Map pinning:** Maps must be individually pinned after struct_ops registration.
- **Privileges:** Bridge CLI requires CAP_BPF + CAP_SYS_ADMIN.
- **Map names:** Truncated to 15 characters by bpftool.

## Controller
- **Userspace-only:** Controller runs in userspace. BPF only enforces gating.
- **Recovery:** Uses rolling window hysteresis; may be slow to detect drift.

## Actions
- **SLEEP:** Uses deferred eligibility (not_before_ns), not true kernel sleep.
- **MIGRATE:** Uses SCX_DSQ_LOCAL dispatch; targeted DSQ pending for true migration.
- **THROTTLE:** Uses reduced slice; not precise bandwidth control.

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
