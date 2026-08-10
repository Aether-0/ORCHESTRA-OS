#!/bin/bash
set -euo pipefail
# ORCHESTRA-OS Real-Machine Benchmark Suite
# Compares CFS vs scx_simple vs ORCHESTRA

OUTDIR="/tmp/orchestra-bench-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUTDIR"
NCPU=$(nproc)

log() { echo "$(date +%H:%M:%S) $*" | tee -a "$OUTDIR/bench.log"; }

cat > "$OUTDIR/results.csv" << 'EOF'
scheduler,workers,duration_s,elapsed_ms,ctx_switches,notes
EOF

# Helper: run workload with given scheduler loaded
run_test() {
    local SCHED=$1 WORKERS=$2 SECS=$3
    log "  $SCHED: $WORKERS workers, ${SECS}s..."
    
    local start_ns=$(date +%s%N)
    for i in $(seq 1 $WORKERS); do
        taskset -c $(( (i-1) % NCPU )) bash -c "
            e=\$((\$(date +%s) + $SECS))
            while [ \$(date +%s) -lt \$e ]; do volatile double x=1; for j in \$(seq 1 100); do x=x*1.0001; done; done
        " &
    done
    for pid in $(jobs -p); do wait $pid 2>/dev/null; done
    local end_ns=$(date +%s%N)
    local ms=$(( (end_ns - start_ns) / 1000000 ))
    
    local ctx=$(grep ctxt /proc/stat | awk '{print $2}')
    echo "$SCHED,$WORKERS,$SECS,$ms,$ctx,completed" >> "$OUTDIR/results.csv"
    log "    ${ms}ms, ctx=$ctx"
}

# === Workloads ===
WORKLOADS=(
    "cpu:1:30"
    "cpu:2:30"
    "cpu:4:30"
    "cpu:8:30"
)

log "=== Real-Machine Benchmark Suite ==="
log "CPU: $NCPU cores  | Output: $OUTDIR"

# ---- CFS Baseline ----
log "--- CFS Baseline ---"
for w in "${WORKLOADS[@]}"; do
    IFS=':' read -r type workers secs <<< "$w"
    run_test "cfs" "$workers" "$secs"
done

# ---- scx_simple ----
if command -v /usr/bin/scx_simple &>/dev/null; then
    log "--- scx_simple ---"
    sudo /usr/bin/scx_simple &
    SCX_PID=$!
    sleep 2
    if [ "$(cat /sys/kernel/sched_ext/state 2>/dev/null)" = "enabled" ]; then
        for w in "${WORKLOADS[@]}"; do
            IFS=':' read -r type workers secs <<< "$w"
            run_test "scx_simple" "$workers" "$secs"
        done
    fi
    sudo kill $SCX_PID 2>/dev/null; wait $SCX_PID 2>/dev/null
    sleep 2
else
    log "scx_simple not installed (dnf install scx_c_schedulers)"
fi

# ---- ORCHESTRA ----
log "--- ORCHESTRA ---"
BPF="/home/vagrant/Documents/ORCHESTRA-OS/kernel/sched_ext/orchestra_scx_stage7.bpf.o"
[ -f "$BPF" ] && sudo bpftool struct_ops register "$BPF" /sys/fs/bpf/bench 2>&1 | tail -1
sleep 2
if [ "$(cat /sys/kernel/sched_ext/state 2>/dev/null)" = "enabled" ]; then
    for w in "${WORKLOADS[@]}"; do
        IFS=':' read -r type workers secs <<< "$w"
        run_test "orchestra" "$workers" "$secs"
    done
    sudo rm -rf /sys/fs/bpf/bench 2>/dev/null
    for l in $(sudo bpftool link list 2>&1 | grep struct_ops | awk -F: '{print $1}'); do
        sudo bpftool link detach id $l 2>/dev/null
    done
fi

log "=== COMPLETE ==="
echo ""
echo "========== RESULTS =========="
cat "$OUTDIR/results.csv"
echo ""
echo "Full results: $OUTDIR"
