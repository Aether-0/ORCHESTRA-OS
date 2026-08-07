# Stage 8A — Exact Kernel: VALIDATED

## Final Build

| Item | Value |
|------|-------|
| Kernel source | v6.12.96 (stable) |
| Build config | x86_64_defconfig + sched_ext/BTF/XFS/E1000/SATA |
| bzImage SHA-256 | `d3d50d26b3d1a91196318a2c99d1c71a859c3171b69276bd26414ae6dfa9e912` |
| Build method | `make -j4` on 4 vCPU, 8 GB RAM, 64 GB disk |

## Root Cause of Previous Boot Failure
BLS entry had incorrect paths: `linux /vmlinuz-6.12.96` instead of `linux /boot/vmlinuz-6.12.96`. Fixed by matching the Fedora BLS entry format with explicit root=UUID and /boot prefix.

## Running Environment

| Item | Value |
|------|-------|
| Running kernel | 6.12.96 (exact build) |
| sched_ext state | disabled (pre-attach) |
| BTF SHA-256 | `7af6be54b981c04e7e57c2043f3cb0247e05e564ff65271138197fd8a91ca458` |
| vmlinux.h SHA-256 | `d3a194c1392011277ba2a7a6403043dc0c9005f427d041d9a9db49797dbc4ad8` |
| ORCHESTRA BPF SHA-256 | `609e6974af2b5cf69571d87332a8c0c29020110ade83a38453263efd9dd68ca0` |

## Exact Alignment Confirmed

| Component | Same Revision? |
|-----------|---------------|
| Running kernel ↔ Source | ✓ v6.12.96 |
| BTF ↔ Running kernel | ✓ |
| vmlinux.h ↔ BTF | ✓ |
| sched_ext headers ↔ Source | ✓ v6.12.96 |
| ORCHESTRA build ↔ Source headers | ✓ |

## Runtime Gates

| Gate | Result |
|------|--------|
| scx_simple 3-cycle | PASS |
| ORCHESTRA attach | PASS (state=enabled) |
| Bridge status | PASS (magic=0x4f524342) |
| Publish gen 1→6 | PASS |
| 5-min stability | PASS |
| Clean unload | PASS (state=disabled) |
| No errors | 0 DSQ, 0 panic, 0 stall |
