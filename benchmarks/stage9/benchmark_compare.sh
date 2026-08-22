#!/usr/bin/env bash
set -euo pipefail

# Historical Stage 9 entry point. Keep the name for existing runbooks, but
# delegate to the maintained real-machine runner so this path inherits its
# exact-TID ownership gate, relative paths, and loader-scoped cleanup.

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)

if [ -n "${STAGE9_EVIDENCE_DIR:-}" ]; then
    export ORCHESTRA_BENCH_OUTDIR=$STAGE9_EVIDENCE_DIR
else
    export ORCHESTRA_BENCH_OUTDIR=/tmp/stage9-benchmarks-$(date +%Y%m%d-%H%M%S)
fi
export ORCHESTRA_WORKERS=${ORCHESTRA_WORKERS:-"1 2 4 8"}
export BENCH_SECS=${BENCH_SECS:-30}
export ORCHESTRA_WORKLOAD_MODE=${ORCHESTRA_WORKLOAD_MODE:-mixed}

set +e
"$REPO_ROOT/benchmarks/real-machine/benchmark_suite.sh" "$@"
runner_status=$?
set -e

python3 - "$ORCHESTRA_BENCH_OUTDIR/results.csv" \
    "$ORCHESTRA_BENCH_OUTDIR/results.json" <<'PY'
import csv
import json
import sys

csv_path, json_path = sys.argv[1:]
with open(csv_path, newline="", encoding="utf-8") as stream:
    rows = list(csv.DictReader(stream))
with open(json_path, "w", encoding="utf-8") as stream:
    json.dump({"results_csv": csv_path, "results": rows}, stream, indent=2)
    stream.write("\n")
PY

echo "Stage 9 results JSON: $ORCHESTRA_BENCH_OUTDIR/results.json"
exit "$runner_status"
