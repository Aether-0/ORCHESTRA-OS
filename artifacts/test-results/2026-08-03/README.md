# ORCHESTRA-OS test evidence - 2026-08-03

This directory contains every text/data test artifact that remained available
locally when the archive was created, plus a fresh full regression capture.

## Evidence map

| Path | Classification | Interpretation |
| --- | --- | --- |
| `benchmark/authoritative-c/` | Authoritative userspace smoke | Exact copy of `/tmp/orchestra-paper-cpu-smoke-v1-20260803-c`; 6/6 validated invocations, source hash `d5ec68...8713`; this is the campaign used by the result report and figures. |
| `benchmark/superseded-a/` | Superseded | Exact copy of complete six-run campaign `-a`, source hash `b03b78...c55a`; it predates final implementation fixes and must not be mixed with the authoritative result. |
| `benchmark/superseded-b/` | Superseded | Exact copy of complete six-run campaign `-b`, source hash `5de386...2193`; it predates final implementation fixes and must not be mixed with the authoritative result. |
| `development-smoke/` | Historical development evidence | CSV/log/stdout/stderr files copied from `/tmp/orchestra-os-testing.1InlRQ`; provenance is incomplete, so these are debugging records rather than experiment evidence. |
| `regression/final/` | Current regression evidence | Fresh `make test` capture after artifact preservation support was added; includes the combined transcript, machine-readable result, and all five integration scenarios' CSV/log files. |
| `regression/pre-repository-artifact-defaults/` | Superseded regression capture | Passing run immediately before the plotting/reporting defaults were changed from `/tmp` to the retained repository artifact. Retained for completeness. |
| `regression/pre-artifact-index-check/` | Superseded regression capture | Passing run with preserved integration CSV/log files immediately before the artifact indexer was added to the top-level syntax checks. Retained for completeness. |
| `regression/pre-integration-artifact-capture/` | Superseded regression transcript | Passing run immediately before integration CSV/log preservation was added. Retained so no test result is silently discarded. |
| `regression/pre-capture-tool-check/` | Superseded regression transcript | Passing run immediately before the capture tool was added to the top-level syntax checks. Retained for completeness. |

## Current regression result

`regression/final/test-result.json` records return code `0`, unchanged input
hashes, the compiler/tool versions, and the merged transcript hash. The run
passed:

- 13/13 named GCC ASan/UBSan unit groups;
- the same 13/13 groups under Clang policy warnings;
- 4/4 benchmark-validator tests; and
- 5/5 integration scenarios covering baseline, ORCHESTRA cadence, tamper
  rejection, rejected-frame controller gating, and bounded signal teardown.

The regression suite is correctness evidence for the named userspace tests. It
does not strengthen the system beyond the **Userspace-validated** claim class.

## Copy and hygiene record

- All three benchmark directory copies passed recursive byte comparison against
  their `/tmp` sources.
- All 22 retained development CSV/log/stdout/stderr files passed byte
  comparison against their source files.
- Seven generated development test executables were deliberately not copied;
  they are rebuildable inputs, not test results. Their source hashes are listed
  below so the exclusion is auditable.
- A text scan found no cookie, authorization, bearer-token, password, API-key,
  client-secret, access-token, refresh-token, or email-address matches.
- Raw provenance retains the local hostname, username/path, process snapshot,
  and hardware metadata because this is a local research archive. Review and
  sanitize a derived copy before public distribution; do not mutate the raw
  evidence.
- The original `/tmp` directories were not deleted.

Excluded development executables:

| File | SHA-256 |
| --- | --- |
| `orchestra_atomic_clang` | `08ccc1796716e02a3dea367fd866a45209bd856fc75a6d85507bbcb7be2a5ad6` |
| `orchestra_atomic_gcc` | `a051f65088d5f07364967aad6c9936a1cedd2cee347a6853a7f4f4b3fced3c3d` |
| `orchestra_release` | `36520d79649dc240a805fe646bd325d430f2b884eca40479a1ab92897ecd8692` |
| `orchestra_san` | `03e23ad0b6df52f05eaaf956622a5fde673efc082a20fd4f0e3a6064c52448f9` |
| `orchestra_v2` | `0aeca6bf63e9a01a6e522c5364306f7aa9f7c72eb8070e89c58c463b8a29884d` |
| `orchestra_v2_clang` | `74fd75d32793fa8b7c097eaa8b8d10eff8cea90473635bf28386c5283d5de7ee` |
| `orchestra_v2_strict` | `3cf28905af15f7455cd8ca8cfa07a004c629a5055690fcbe7e9b1917284f0f01` |

`SHA256SUMS` covers every retained evidence file except the checksum and
inventory files themselves. `inventory.json` records counts, sizes, category
totals, and the checksum-manifest identity.
