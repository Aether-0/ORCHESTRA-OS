#!/usr/bin/env bash
set -euo pipefail

# Full comparison entry point. The common benchmark runner provides the
# location-independent paths, barriered launch protocol, exact-TID ownership
# gate, and loader-scoped attach/unload lifecycle.
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if [[ -v ORCHESTRA_WORKERS ]]; then
    : "${ORCHESTRA_WORKERS:?}"
else
    ORCHESTRA_WORKERS="1 2 4 8"
fi
export ORCHESTRA_WORKERS

if [[ -v BENCH_SECS ]]; then
    : "${BENCH_SECS:?}"
else
    BENCH_SECS=30
fi
export BENCH_SECS

if [[ -v ORCHESTRA_WORKLOAD_MODE ]]; then
    : "${ORCHESTRA_WORKLOAD_MODE:?}"
else
    ORCHESTRA_WORKLOAD_MODE=mixed
fi
export ORCHESTRA_WORKLOAD_MODE

exec "$SCRIPT_DIR/benchmark_suite.sh" "$@"
