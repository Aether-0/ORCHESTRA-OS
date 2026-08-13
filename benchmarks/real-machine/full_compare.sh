#!/bin/bash
set -euo pipefail
# ORCHESTRA-OS Full Real-Machine Comparison
# Tests CFS vs scx_simple vs ORCHESTRA across multiple dimensions

OUT="/tmp/orchestra-compare-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUT"
NCPU=$(nproc)
BPF="/home/vagrant/Documents/ORCHESTRA-OS/kernel/sched_ext/orchestra_scx_stage7.bpf.o"
BRIDGE="${ORCHESTRA_BRIDGE:-/home/vagrant/Documents/ORCHESTRA-OS/kernel/sched_ext/bridge/orchestra_bridge}"

log() { echo "$(date +%H:%M:%S) $*" | tee -a "$OUT/run.log"; }

cat > "$OUT/results.csv" << 'EOF'
scheduler,test,workers,elapsed_ms,ctx_switches,notes
EOF

run_test() {
    local SCHED=$1 LABEL=$2 WORKERS=$3 SECS=$4 TYPE=$5
    log "  $SCHED/$LABEL: $WORKERS $TYPE workers × ${SECS}s"
    
    local PIDS=()
    local start_ns=$(date +%s%N)
    local ctx0
    ctx0=$(awk '/^ctxt/{print $2}' /proc/stat)
    for i in $(seq 1 $WORKERS); do
        case $TYPE in
            cpu)
                taskset -c $(( (i-1) % NCPU )) bash -c "
                    e=\$((\$(date +%s) + $SECS))
                    while [ \$(date +%s) -lt \$e ]; do :; done
                " &
                PIDS+=($!) ;;
            mixed)
                if [ $((i % 2)) -eq 0 ]; then
                    taskset -c $(( (i-1) % NCPU )) bash -c "
                        e=\$((\$(date +%s) + $SECS))
                        while [ \$(date +%s) -lt \$e ]; do :; done
                    " &
                    PIDS+=($!)
                else
                    taskset -c $(( (i-1) % NCPU )) bash -c "
                        e=\$((\$(date +%s) + $SECS))
                        while [ \$(date +%s) -lt \$e ]; do
                            dd if=/dev/zero of=/tmp/cmp-\$i bs=4k count=5 2>/dev/null
                            sleep 0.05
                        done
                    " &
                    PIDS+=($!)
                fi ;;
        esac
    done
    if [ "$SCHED" = "orchestra" ] && [ -x "${ORCHESTRA_BRIDGE:-/home/vagrant/Documents/ORCHESTRA-OS/kernel/sched_ext/bridge/orchestra_bridge}" ]; then
        local BR="${ORCHESTRA_BRIDGE:-/home/vagrant/Documents/ORCHESTRA-OS/kernel/sched_ext/bridge/orchestra_bridge}"
        for pid in "${PIDS[@]}"; do
            sudo "$BR" --opt-in --target-pid "$pid" >/dev/null 2>&1 || true
            sudo "$BR" --publish --action RUN --target-pid "$pid" >/dev/null 2>&1 || true
        done
    fi
    for pid in "${PIDS[@]}"; do wait "$pid" 2>/dev/null || true; done
    local end_ns=$(date +%s%N)
    local ms=$(( (end_ns - start_ns) / 1000000 ))
    local ctx1 ctxd
    ctx1=$(awk '/^ctxt/{print $2}' /proc/stat)
    ctxd=$((ctx1 - ctx0))
    echo "$SCHED,$LABEL,$WORKERS,$ms,$ctxd,ok" >> "$OUT/results.csv"
    log "    => ${ms}ms ctx_delta=$ctxd"
}

# ====== MAIN ======
log "=== Full Comparison ==="
log "Machine: $(uname -r) | CPUs: $NCPU"

# ---- CFS ----
log "--- CFS Baseline ---"
for w in 1 2 4 8; do
    [ $w -le $NCPU ] || break
    run_test "cfs" "cpu_${w}w" "$w" 30 cpu
    run_test "cfs" "mixed_${w}w" "$w" 30 mixed
done

# ---- scx_simple ----
if [ -x /usr/bin/scx_simple ]; then
    log "--- scx_simple ---"
    sudo /usr/bin/scx_simple > /dev/null 2>&1 &
    SCX=$!
    sleep 2
    [ "$(cat /sys/kernel/sched_ext/state 2>/dev/null)" = "enabled" ] || { log "scx_simple failed"; sudo kill $SCX 2>/dev/null; }
    for w in 1 2 4 8; do
        [ $w -le $NCPU ] || break
        run_test "scx_simple" "cpu_${w}w" "$w" 30 cpu
    done
    sudo kill $SCX 2>/dev/null || true
    sleep 2
    for l in $(sudo bpftool link list 2>&1 | grep struct_ops | awk -F: '{print $1}'); do
        sudo bpftool link detach id $l 2>/dev/null || true
    done
    sleep 1
fi

# ---- ORCHESTRA ----
if [ -f "$BPF" ]; then
    log "--- ORCHESTRA ---"
    sudo rm -rf /sys/fs/bpf/* 2>/dev/null
    for l in $(sudo bpftool link list 2>&1 | grep struct_ops | awk -F: '{print $1}'); do
        sudo bpftool link detach id $l 2>/dev/null
    done
    sudo bpftool struct_ops register "$BPF" /sys/fs/bpf/cmp 2>&1 | tail -1
    sleep 2
    
    if [ "$(cat /sys/kernel/sched_ext/state 2>/dev/null)" = "enabled" ]; then
        sudo "$BRIDGE" --pin-maps || true
        for w in 1 2 4 8; do
            [ $w -le $NCPU ] || break
            run_test "orchestra" "cpu_${w}w" "$w" 30 cpu
        done
    fi
    
    sudo rm -rf /sys/fs/bpf/* 2>/dev/null
    for l in $(sudo bpftool link list 2>&1 | grep struct_ops | awk -F: '{print $1}'); do
        sudo bpftool link detach id $l 2>/dev/null
    done
fi

log "=== COMPLETE ==="
echo "" && echo "======== RESULTS ========" && cat "$OUT/results.csv"
echo "" && echo "Full: $OUT"
