#!/bin/bash
set -euo pipefail
# ORCHESTRA-OS Real-Machine Benchmark Suite
# Compares CFS vs scx_simple vs ORCHESTRA (owned SCHED_EXT workers).
# Context switches are per-run deltas. scx_simple is not waited as a job.

OUTDIR="/tmp/orchestra-bench-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUTDIR"
NCPU=$(nproc)
BPF="${ORCHESTRA_BPF:-/home/vagrant/Documents/ORCHESTRA-OS/kernel/sched_ext/orchestra_scx_stage7.bpf.o}"
BRIDGE="${ORCHESTRA_BRIDGE:-/home/vagrant/Documents/ORCHESTRA-OS/kernel/sched_ext/bridge/orchestra_bridge}"
SECS="${BENCH_SECS:-8}"

log() { echo "$(date +%H:%M:%S) $*" | tee -a "$OUTDIR/bench.log"; }

echo "scheduler,workers,duration_s,elapsed_ms,ctx_delta,enqueue,running,owned,notes" > "$OUTDIR/results.csv"

tel_field() {
    local f="$1"
    sudo bpftool map dump name bridge_telemetr 2>/dev/null | python3 -c "
import sys, json
d=json.load(sys.stdin)[0]['value']
print(d.get('$f', 0))
" 2>/dev/null || echo 0
}

run_test() {
    local SCHED=$1 WORKERS=$2 DSECS=$3
    log "  $SCHED: $WORKERS workers, ${DSECS}s..."

    local ctx0
    ctx0=$(awk '/^ctxt/{print $2}' /proc/stat)
    local PIDS=()
    local start_ns end_ns ms ctx1 ctxd
    start_ns=$(date +%s%N)
    for i in $(seq 1 "$WORKERS"); do
        taskset -c $(( (i-1) % NCPU )) bash -c "
            e=\$((\$(date +%s) + $DSECS))
            while [ \$(date +%s) -lt \$e ]; do :; done
        " &
        PIDS+=($!)
    done

    local enq=0 running=0 owned=n/a notes=completed
    if [ "$SCHED" = "orchestra" ] && [ -x "$BRIDGE" ]; then
        for pid in "${PIDS[@]}"; do
            sudo "$BRIDGE" --opt-in --target-pid "$pid" >/dev/null 2>&1 || true
            sudo "$BRIDGE" --publish --action RUN --target-pid "$pid" >/dev/null 2>&1 || true
        done
    fi

    for pid in "${PIDS[@]}"; do wait "$pid" 2>/dev/null || true; done
    end_ns=$(date +%s%N)
    ms=$(( (end_ns - start_ns) / 1000000 ))
    ctx1=$(awk '/^ctxt/{print $2}' /proc/stat)
    ctxd=$((ctx1 - ctx0))

    if [ "$SCHED" = "orchestra" ]; then
        enq=$(tel_field enqueue_count)
        running=$(tel_field running_count)
        if [ "$enq" -gt 0 ] && [ "$running" -gt 0 ]; then
            owned=yes
        else
            owned=no
            notes="ownership-gate-failed"
        fi
    fi

    echo "$SCHED,$WORKERS,$DSECS,$ms,$ctxd,$enq,$running,$owned,$notes" >> "$OUTDIR/results.csv"
    log "    ${ms}ms ctx_delta=$ctxd enq=$enq running=$running owned=$owned"
}

WORKLOADS=(
    "cpu:1:${SECS}"
    "cpu:2:${SECS}"
    "cpu:4:${SECS}"
)

log "=== Real-Machine Benchmark Suite ==="
log "CPU: $NCPU cores  | Output: $OUTDIR | duration=${SECS}s"

log "--- CFS Baseline ---"
for w in "${WORKLOADS[@]}"; do
    IFS=':' read -r type workers secs <<< "$w"
    run_test "cfs" "$workers" "$secs"
done

if [ -x /usr/bin/scx_simple ]; then
    log "--- scx_simple ---"
    sudo /usr/bin/scx_simple >/dev/null 2>&1 &
    SCX_PID=$!
    sleep 2
    if [ "$(cat /sys/kernel/sched_ext/state 2>/dev/null)" = "enabled" ]; then
        for w in "${WORKLOADS[@]}"; do
            IFS=':' read -r type workers secs <<< "$w"
            run_test "scx_simple" "$workers" "$secs"
        done
    fi
    sudo kill "$SCX_PID" 2>/dev/null || true
    sleep 2
    for l in $(sudo bpftool link list 2>&1 | grep struct_ops | awk -F: '{print $1}'); do
        sudo bpftool link detach id "$l" 2>/dev/null || true
    done
    sleep 1
else
    log "scx_simple not installed (dnf install scx_c_schedulers)"
fi

log "--- ORCHESTRA ---"
if [ -f "$BPF" ]; then
    sudo rm -rf /sys/fs/bpf/bench /sys/fs/bpf/bridge_* 2>/dev/null || true
    for l in $(sudo bpftool link list 2>&1 | grep struct_ops | awk -F: '{print $1}'); do
        sudo bpftool link detach id "$l" 2>/dev/null || true
    done
    sudo bpftool struct_ops register "$BPF" /sys/fs/bpf/bench 2>&1 | tail -1
    sleep 2
    if [ "$(cat /sys/kernel/sched_ext/state 2>/dev/null)" = "enabled" ]; then
        if [ -x "$BRIDGE" ]; then
            sudo "$BRIDGE" --pin-maps || true
        fi
        for w in "${WORKLOADS[@]}"; do
            IFS=':' read -r type workers secs <<< "$w"
            run_test "orchestra" "$workers" "$secs"
        done
        sudo rm -rf /sys/fs/bpf/bench /sys/fs/bpf/bridge_* 2>/dev/null || true
        for l in $(sudo bpftool link list 2>&1 | grep struct_ops | awk -F: '{print $1}'); do
            sudo bpftool link detach id "$l" 2>/dev/null || true
        done
    fi
else
    log "BPF object missing: $BPF"
fi

log "=== COMPLETE ==="
echo ""
echo "========== RESULTS =========="
cat "$OUTDIR/results.csv"
echo ""
echo "Full results: $OUTDIR"
