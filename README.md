# ORCHESTRA-OS

Predictive, cryptographically protected, hierarchical, signal-coordinated
scheduling architecture — research program repository.

**Maturity:** userspace-validated prototype. Linux still performs final dispatch.
This is not a kernel scheduler, production security result, or deployment-ready
system.

## Canonical userspace path

| Component | Location |
|-----------|----------|
| Implementation | `orchestra_paper_cpu_demo/orchestra_paper_cpu.c` |
| Unit tests | `tests/unit/` |
| Integration tests | `tests/integration/` |
| Benchmark runner | `tools/benchmark/run_paper_cpu_benchmark.py` |
| Experiment manifests | `experiments/manifests/` |
| Metric schemas | `experiments/schemas/` |
| Architecture decisions | `docs/adr/` |

Do not treat `orchestra_real_cpu_demo/` as the canonical implementation path.

## Build and test

```bash
make            # build canonical binary
make test       # static checks, unit tests, integration tests
make clean      # remove build artifacts
```

## Research governance

See [AGENTS.md](AGENTS.md) for work-package scope, invariants, claim classes,
and development protocol.

## Artifacts

Bounded experiment evidence is retained under `artifacts/test-results/` with
manifests and provenance records. Raw traces are immutable once captured; see
[artifacts/README.md](artifacts/README.md).
