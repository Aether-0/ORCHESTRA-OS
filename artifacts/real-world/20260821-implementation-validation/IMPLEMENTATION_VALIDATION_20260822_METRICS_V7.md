# ORCHESTRA-OS metrics-v7 implementation validation

Date: 2026-08-22  
Repository commit under test: `85c500afed8cb6f4e8ac480e536b439af870ec2f`  
Working tree: intentionally dirty; unrelated user changes were preserved  
Claim class: `USERSPACE_VALIDATED` / pipeline contract validation only

## Finding addressed

The current userspace binary emitted the 121-column
`orchestra.paper_cpu.metrics/v7` CSV contract, while the benchmark runner
previously supported only v2-v5 and the v7 schema file did not resolve its
append-only column definition. That caused valid v7 output to be rejected or
excluded before it could contribute to a bounded summary.

The first end-to-end attempt is preserved at
`/tmp/orchestra-benchmark-v7-20260822`. It completed all six invocations but
validated only 3/6. The three ORCHESTRA rows were rejected by a runner-side
controller-causality expectation: the runner expected jitter to increase for an
S4 event even when the current C implementation correctly froze jitter at its
floor because S2 was below the 0.82 compliance threshold. This failure was
diagnosed and retained rather than overwritten.

## Implementation

- Added append-only v6 and v7 schema resolution in
  `tools/benchmark/run_paper_cpu_benchmark.py`.
- Added strict expected-column-count checks to append-only manifests.
- Added v6 policy-lifecycle fields and semantic validation.
- Added v7 conditioned-coordination semantics: `S3_conditioned` is canonical
  S3, canonical S4 is `min(historical S4, S4_burst)`, and
  `coordination_semantics_version` must equal 7.
- Added bounded v6/v7 exploratory manifests with exact 120/121-column
  contracts.
- Extended the independent CSV validator to check v6/v7 policy modes,
  versions, update permissions, lifecycle statuses, counters, and v7
  coordination semantics.
- Corrected the runner controller expectation to match the source behavior:
  jitter can increase for S4 only when S2 is at least 0.82.
- Updated repository documentation and integration status text so v7 is not
  described as an unimplemented or v2-v5-only contract.

## Evidence

The isolated benchmark validator suite passed 24/24 tests, including:

- append-only v6/v7 schema resolution;
- exact v6/v7 manifest column counts;
- valid v7 conditioned-coordination rows;
- policy-mode consistency rejection;
- v7 summary aggregation.

The final fresh end-to-end run is preserved at
`/tmp/orchestra-benchmark-v7-20260822-r4`:

| Result | Value |
|---|---:|
| Schema | `orchestra.paper_cpu.metrics/v7` |
| Expected invocations | 6 |
| Attempted invocations | 6 |
| Validated invocations | 6 |
| Failed or excluded | 0 |
| Independent CSV-validator passes | 6/6 |
| Policy lifecycle mode-level summaries | present for baseline and orchestra |
| Modes | 3 baseline, 3 orchestra |
| Workers / duration | 4 / 4 seconds |
| Root or SCHED_FIFO required | No |

The result is a descriptive, unpaired, endogenous userspace pipeline result.
It does not establish a causal performance improvement, Linux scheduler
ownership, kernel dispatch compliance, or hard-real-time behavior.

The processed v7 summary also carries the lifecycle result: both modes report
`TRAIN` and coordination semantics version 7; baseline ends at policy
generation 0, while the three ORCHESTRA invocations end at generation 2 with
an average of 21 applied policy-update rows per invocation. This is evidence
that the userspace lifecycle fields are propagated into the invocation summary,
not evidence of a kernel controller.

The final repository gates also passed:

| Gate | Result |
|---|---|
| `make check` | PASS |
| `make test` | PASS: GCC/Clang/legacy unit and stress paths, 24 benchmark-validator tests, 4 publication-runner tests, 34 CSV-validator tests, all integration scenarios |
| `make` | PASS |
| v7 CSV validator on a fresh run | PASS: 40 rows |
| JSON/Python syntax checks | PASS |
| sched_ext source safety invariants | PASS |
| kernel configuration check | PASS: required running-kernel options present |
| target-matched Stage 7 BPF/bridge/loader build | PASS: `/tmp/orchestra-stage7-final-20260822/build-manifest.txt` |
| `git diff --check` | PASS |

The target-matched build used running kernel `7.0.12+kali-amd64`, source
version `7.0.12`, and the running kernel's BTF. It produced the BPF object,
bridge, and loader without modifying repository sources. Privileged verifier,
attach, ownership, and unload execution was not attempted because
non-interactive root authorization is unavailable.

## Reproduction

```bash
python3 tests/unit/test_benchmark_validator.py

python3 tools/benchmark/run_paper_cpu_benchmark.py \
  --manifest experiments/manifests/paper_cpu_exploratory_v7.json \
  --schema experiments/schemas/paper_cpu_metrics_v7.json \
  --binary orchestra_paper_cpu_demo/orchestra_paper_cpu \
  --source orchestra_paper_cpu_demo/orchestra_paper_cpu.c \
  --repository-root . \
  --output-dir /tmp/orchestra-benchmark-v7-20260822-r4
```

The successful result's machine-readable summary is
`/tmp/orchestra-benchmark-v7-20260822-r4/benchmark_result.json`; its processed
summary is under `/tmp/orchestra-benchmark-v7-20260822-r4/processed/`.

## Remaining boundary

This slice fixes the userspace metrics contract and its evidence path. It does
not implement the still-missing kernel predictor, kernel-computed S1-S4/Q,
feedback controller, full Hybrid Safety Layer, NUMA tier, or distributed
tier. Bare-metal verifier/attach/ownership testing also remains blocked by the
absence of non-interactive root authorization on the test machine.
