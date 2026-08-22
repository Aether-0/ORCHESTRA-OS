#!/usr/bin/env bash
set -euo pipefail

# Safe compatibility entry point for the historical Stage 7 reproduction
# name. The old implementation used raw struct_ops registration, source-tree
# generated headers, global bpffs cleanup, and global link detachment. The
# maintained P0 runner now performs the current loader-scoped build, exact-TID
# ownership gate, forward-progress check, and all five action probes.

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
EVIDENCE_DIR=${STAGE7_EVIDENCE_DIR:-"/tmp/stage7-evidence-$(date +%Y%m%d-%H%M%S)"}

exec "$SCRIPT_DIR/p0_ownership_retest.sh" "$EVIDENCE_DIR"
