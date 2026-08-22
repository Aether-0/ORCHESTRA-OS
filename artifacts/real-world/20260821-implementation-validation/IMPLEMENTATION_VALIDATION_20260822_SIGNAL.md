# ORCHESTRA-OS implementation validation — 2026-08-22 signal bridge follow-up

This is an additive follow-up to `IMPLEMENTATION_VALIDATION.md`; the earlier
results and first failures remain unchanged.

## Implemented slice

- Added the exact-schema `orch_signal` `ARRAY[1]` map carrying a 152-byte,
  fixed-point `bridge_signal_frame`.
- Added bridge publication with `BPF_F_LOCK`, exact readback, scheduler-epoch
  binding, strictly increasing sequence checks, bounded expiry, and range
  validation for all permille fields.
- Added BPF-side signal validation for ABI/schema, known flags, required
  metrics/controller fields, prediction flag coherence, epoch, publication
  age, expiry, sequence, action/range bounds, and controller/policy coherence.
- Added signal accept/invalid/stale telemetry and the fail-closed
  `BRIDGE_DIRECTIVE_F_REQUIRE_SIGNAL` directive gate.
- Extended the existing userspace `--kernel-bridge` stream to publish one
  converted signal frame before its per-task directives and require that frame
  for every directive in the tick. The userspace HMAC remains outside the BPF
  trust boundary; BPF does not claim to verify it.
- Updated map schemas, loader pinning, bridge status output, source invariants,
  ABI tests, ADR/status/readme documentation, and the stream ABI contract.
- Added a bridge admission guard that refuses adaptive directives for current
  `SCHED_FIFO`, `SCHED_RR`, or `SCHED_DEADLINE` targets and fails closed if the
  target policy cannot be read.

## Validation

| Check | Result | Evidence |
|---|---|---|
| Initial regression after ABI change | FAIL, preserved | `make test` stopped at the old unit assertion expecting an 88-byte stream request |
| Corrected bridge ABI/unit tests | PASS | `make test-unit`, GCC/Clang/legacy bridge parser and ABI tests |
| `python3 tests/unit/test_orchestra_scx_source.py` | PASS | source safety invariants |
| `make check` | PASS | exit 0 |
| Final `make test` | PASS | 30/30 named unit tests across compiler/transport passes; 21 benchmark validator tests; 4 signal-publication runner tests; 34 CSV validator tests; all five integration scenarios |
| Userspace link build | PASS | `make` |
| Exact target-matched BPF/bridge/loader build | PASS | `/tmp/orchestra-stage7-signal-20260822-r3/build-manifest.txt` |
| RT-policy guard unit coverage | PASS | bridge parser/ABI test asserts FIFO/RR/DEADLINE rejection and normal/batch/idle allowance |
| Runtime scheduler state after validation | PASS | running kernel `7.0.12+kali-amd64`; `/sys/kernel/sched_ext/state=disabled`; `/sys/fs/bpf` contains only its root directory |

## Exact build provenance

```text
running_kernel=7.0.12+kali-amd64
source_version=7.0.12
bpf_uapi_sha256=e10e5d9389b83767a9333e5d53a4c5524fe29ff470ef3c5e50aa6b4cddbb29c1
bpf_doc_sha256=7e3aa3b9cac901b366330e19e5b9b7bd9bb9095e167b74b67c3014c7b1d300f3
bpf_helper_defs_sha256=ebcd44514b37cbd4459b5b637dcb39a43d9adee94496c3afe2ee5219b5c8a3a5
vmlinux_sha256=96b223c8eaa9763f6caa0998188cf632aa0133c096bf526edc0043db3e675a51
bpf_object_sha256=6fb4d679c8a628c8c8f84faa5162a020514029ad85023d3d9d001a846676a689
bridge_sha256=5515ee39a33717dc903c887cbf6de46e216db6f9e083173a430c2f14a0ece717
loader_sha256=74848ef20c08c9baf752c90cd88cf3e2f879c3572c6611a5c6a1b676f6012926
```

The BPF object is an eBPF ELF relocatable and exposes the eight expected map
symbols, including `orch_signal`. No verifier, attach, ownership, effective
action, unload, or fault-recovery claim is promoted here because privileged
non-interactive root/sudo access remains unavailable.

## Claim boundary after this slice

The signal map and required-signal gate are `KERNEL_PROTOTYPED`. They do not
upgrade the project to authenticated kernel signal-bus validation,
kernel-computed prediction, kernel-computed S1/S2/S3/S4/Q, kernel feedback
control, full RT/Hybrid Safety validation, NUMA, distributed scheduling, or
deployment readiness. The RT guard is only bridge admission protection.
