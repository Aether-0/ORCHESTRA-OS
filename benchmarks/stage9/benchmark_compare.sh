#!/bin/bash
set -euo pipefail
# ORCHESTRA-OS Stage 9 — Production Benchmark Suite
# Compares CFS baseline vs scx_simple vs ORCHESTRA

SCHED_DIR="$HOME/Documents/ORCHESTRA-OS/kernel/sched_ext"
KSRC="${ORCHESTRA_KERNEL_SRC:-$HOME/src/linux-v6.12.96}"
EVDIR="$HOME/stage9-benchmarks-$(date +%Y%m%d-%H%M%S)"
RESULTS_CSV="$EVDIR/results.csv"
RESULTS_JSON="$EVDIR/results.json"
TIMESTAMP=$(date -Iseconds)

log() { echo "$(date +%H:%M:%S) $*"; }

# ======== Setup ========
setup() {
    mkdir -p "$EVDIR"
    {
        echo "timestamp: $TIMESTAMP"
        echo "kernel: $(uname -r)"
        echo "cpus: $(nproc)"
        echo "ram_mb: $(free -m | awk '/Mem/{print $2}')"
        echo "os: $(cat /etc/os-release | head -3 | tr '\n' ' ')"
        echo "btf: $(sha256sum /sys/kernel/btf/vmlinux 2>/dev/null | awk '{print $1}')"
    } > "$EVDIR/environment.txt"
    
    cd "$SCHED_DIR"
    sudo rm -rf /sys/fs/bpf/* 2>/dev/null || true
    for l in $(sudo bpftool link list 2>&1 | grep struct_ops | awk -F: '{print $1}'); do sudo bpftool link detach id $l 2>/dev/null; done
    sleep 1
}

# ======== CPU-bound workload ========
run_cpu_workload() {
    local NAME=$1 DURATION=$2
    log "  CPU workload: $NAME ($DURATION sec)"
    
    local start_ns=$(date +%s%N)
    local workers=$(nproc)
    
    # Spawn CPU-bound workers
    for i in $(seq 1 $workers); do
        taskset -c $((i-1)) bash -c "s=0; e=\$(($(date +%s) + $DURATION)); while [ \$(date +%s) -lt \$e ]; do :; done" &
    done
    for pid in $(jobs -p); do wait $pid 2>/dev/null; done
    
    local end_ns=$(date +%s%N)
    local elapsed=$(( (end_ns - start_ns) / 1000000 ))
    local ctx=$(grep ctxt /proc/stat 2>/dev/null | awk '{print $2}' || echo 0)
    
    echo "$TIMESTAMP,$NAME,cpu,$workers,$elapsed,$ctx" >> "$RESULTS_CSV"
    log "    elapsed=${elapsed}ms ctx=$ctx"
}

# ======== Mixed workload ========
run_mixed_workload() {
    local NAME=$1 DURATION=$2
    log "  Mixed workload: $NAME ($DURATION sec)"
    
    local workers=$(nproc)
    local half=$((workers/2))
    [ $half -lt 1 ] && half=1
    
    local start_ns=$(date +%s%N)
    for i in $(seq 1 $half); do
        taskset -c $((i-1)) bash -c "e=\$(($(date +%s) + $DURATION)); while [ \$(date +%s) -lt \$e ]; do :; done" &
    done
    for i in $(seq $((half+1)) $workers); do
        taskset -c $((i-1)) bash -c "e=\$(($(date +%s) + $DURATION)); while [ \$(date +%s) -lt \$e ]; do sleep 0.01; done" &
    done
    for pid in $(jobs -p); do wait $pid 2>/dev/null; done
    
    local end_ns=$(date +%s%N)
    local elapsed=$(( (end_ns - start_ns) / 1000000 ))
    
    echo "$TIMESTAMP,$NAME,mixed,$workers,$elapsed,0" >> "$RESULTS_CSV"
    log "    elapsed=${elapsed}ms"
}

# ======== CFS Baseline ========
run_cfs() {
    log "=== CFS BASELINE ==="
    echo "scheduler,workload,workers,elapsed_ms,ctx_switches" > "$RESULTS_CSV"
    run_cpu_workload "cfs" 10
    run_mixed_workload "cfs" 10
}

# ======== scx_simple ========
run_scx_simple() {
    log "=== scx_simple ==="
    timeout 5s sudo /usr/bin/scx_simple 2>&1 | tail -1 || true
    sleep 2
    [ "$(cat /sys/kernel/sched_ext/state)" = "enabled" ] || { log "scx_simple failed to enable"; return 1; }
    
    run_cpu_workload "scx_simple" 10
    run_mixed_workload "scx_simple" 10
    
    sudo kill $(pgrep -f scx_simple) 2>/dev/null || true
    sleep 2
    for l in $(sudo bpftool link list 2>&1 | grep struct_ops | awk -F: '{print $1}'); do sudo bpftool link detach id $l 2>/dev/null; done
}

# ======== ORCHESTRA ========
run_orchestra() {
    log "=== ORCHESTRA ==="
    sudo bpftool struct_ops register orchestra_scx_stage7.bpf.o /sys/fs/bpf/orch9 2>&1 | tail -1
    sleep 2
    [ "$(cat /sys/kernel/sched_ext/state)" = "enabled" ] || { log "ORCHESTRA failed to enable"; return 1; }
    
    for m in bridge_control_ bridge_directiv bridge_telemetr bridge_task_map; do
        ID=$(sudo bpftool map list 2>&1 | grep -m1 "name $m" | awk '{print $1}' | tr -d ':')
        [ -n "$ID" ] && sudo bpftool map pin id $ID "/sys/fs/bpf/$m" 2>/dev/null
    done
    
    sudo ./bridge/orchestra_bridge --publish --action RUN --target-pid 1 2>&1 | tail -1
    
    run_cpu_workload "orchestra" 10
    run_mixed_workload "orchestra" 10
    
    sudo rm -rf /sys/fs/bpf/* 2>/dev/null
    for l in $(sudo bpftool link list 2>&1 | grep struct_ops | awk -F: '{print $1}'); do sudo bpftool link detach id $l 2>/dev/null; done
}

# ======== JSON export ========
export_json() {
    python3 -c "
import json
with open('$RESULTS_CSV') as f:
    lines = [l.strip().split(',') for l in f if l.strip()]
header, rows = lines[0], lines[1:]
results = [dict(zip(header, r)) for r in rows]
with open('$RESULTS_JSON', 'w') as f:
    json.dump({'benchmark_time': '$TIMESTAMP', 'results': results}, f, indent=2)
" 2>/dev/null
    log "JSON: $RESULTS_JSON"
}

# ======== Main ========
main() {
    setup
    run_cfs
    run_scx_simple
    run_orchestra
    export_json
    log "=== COMPLETE ==="
    log "CSV: $RESULTS_CSV"
    log "JSON: $RESULTS_JSON"
    cat "$RESULTS_CSV"
}
main "$@"
