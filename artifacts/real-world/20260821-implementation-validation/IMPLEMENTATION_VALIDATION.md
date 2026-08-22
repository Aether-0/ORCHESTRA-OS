# ORCHESTRA-OS implementation validation — 2026-08-21

## Scope

This validation follows the 2026-08-21 real-machine findings. It implements
evidence-backed correctness and safety fixes without claiming kernel runtime
validation where the host cannot provide it.

Repository revision at validation time:

```text
85c500afed8cb6f4e8ac480e536b439af870ec2f
```

The working tree was intentionally dirty before this work. Existing user
changes and unrelated untracked files were preserved.

## Implemented changes

- Added exact-TID filtering and lifecycle fields to `bridge --status` so
  ownership gates can distinguish accepted, dispatched, running, effective,
  fallback, and timing evidence for one task. Targeted status now resolves the
  live TGID/TID/start-boottime identity and filters map records by the complete
  identity rather than TID alone.
- Retired an exact released SLEEP generation to RUN, while preserving any
  newer generation, so an expired one-shot directive is not reused on later
  enqueues.
- Reworked the maintained benchmark and stress runners to use repository-
  relative paths, barriered launch, exact-TID ownership admission, bounded
  watchdogs, scoped cleanup, storage accounting, and thermal monitoring.
- Corrected benchmark storage-after capture so it is taken after owned workers,
  helper schedulers, and any ORCHESTRA unload have completed.
- Made CPU placement follow the process's allowed CPU set instead of assuming
  that allowed CPUs begin at ID 0.
- Removed the unsafe per-worker memory arithmetic and explicitly block the
  ORCHESTRA memory phase when child identities cannot be proven.
- Added the target-matched out-of-tree Stage 7 builder with explicit input
  provenance and no package installation or broad bpffs cleanup.
- Changed the fixed-iteration workload to return conventional success after
  completing its work; worker exit status and stderr are now retained by the
  benchmark runner.
- Extended syntax/source checks and updated the current-state and benchmark
  documentation.

## Validation results

| Check | Result | Evidence |
|---|---|---|
| `make check` | PASS | command completed with exit 0 |
| `make test` | PASS | 30/30 named unit tests in GCC/Clang and legacy transport passes; 21 benchmark-runner tests; 4 signal-publication runner tests; 34 CSV-validator tests; all five integration scenarios |
| Target-matched Stage 7 build | PASS | `/tmp/orchestra-stage7-postfix.c6WjqJ/build-manifest.txt` |
| BPF artifact type | PASS | eBPF ELF relocatable object produced |
| CFS benchmark smoke | PASS | `/tmp/orchestra-bench-affinity.bQo4EJ/results.csv` |
| Mixed benchmark smoke / Stage 9 JSON | PASS | `/tmp/orchestra-stage9-validation.fN9fcA/results.csv` and `results.json` |
| CFS stress smoke | PASS | `/tmp/orchestra-stress-affinity.1W6zA3/results.csv` |
| Post-fix CFS stress smoke | PASS | `/tmp/orchestra-stress-postfix.BlDh0Y/results.csv`; CPU/I/O/mixed pass, memory explicitly blocked for missing `stress(1)` |
| Post-fix benchmark smoke | PASS / BLOCKED by capability | `/tmp/orchestra-bench-postfix.1vJMmd/results.csv`; CFS rows complete, ORCHESTRA blocked because the in-tree BPF object is absent |
| P0 privileged attach/ownership gate | BLOCKED | `/tmp/orchestra-p0-validation.7PMAFF/results.csv` reports `BLOCKED_PRIVILEGE` |

The build used the running `7.0.12+kali-amd64` kernel BTF, a source export
reporting version `7.0.12`, the exact installed 7.0.12 UAPI header, and an
explicit helper generator. The manifest records these inputs and hashes:

```text
bpf_uapi_sha256=e10e5d9389b83767a9333e5d53a4c5524fe29ff470ef3c5e50aa6b4cddbb29c1
bpf_doc_sha256=7e3aa3b9cac901b366330e19f5e9b7bd9bb9095e167b74b67c3014c7b1d300f3
bpf_helper_defs_sha256=ebcd44514b37cbd4459b5b637dcb39a43d9adee94496c3afe2ee5219b5c8a3a5
vmlinux_sha256=96b223c8eaa9763f6caa0998188cf632aa0133c096bf526edc0043db3e675a51
bpf_object_sha256=656d501067eb55522294636adac585f48745a283b576b96258d7c3b2b7db9dba
bridge_sha256=3ad9d45bee7ea51ef902a1efd443c1d064c4f4b93b7fd91812cdf10cb6df7882
loader_sha256=df4f7d994304482b1973bd2832abab9e13a0b82a710b67700de8dcbfd1d64392
```

## Environment boundary

- `sched_ext` remained `disabled` before and after all tests.
- `/sys/fs/bpf` contained only its root directory at the final check.
- `sudo -n true` failed because a terminal/password is required.
- `stress(1)` and `scx_simple` are not installed; affected phases remain
  explicitly blocked.
- No package, kernel, BIOS, sysctl, thermal, or persistent BPF configuration
  was changed.

## Remaining claims

The privileged verifier/attach, exact ownership, effective action, unload,
fault-recovery, and comparison phases remain unvalidated on this session.
The kernel prototype still does not implement the authenticated kernel signal
bus, predictor, kernel S1/S2/S3/S4/Q, feedback controller, full Hybrid Safety
Layer, NUMA tier, or distributed tier. The new code improves test validity and
runtime safety; it does not upgrade those claim classes.
