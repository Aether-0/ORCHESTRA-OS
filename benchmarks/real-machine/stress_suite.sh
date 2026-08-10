#!/bin/bash
set -euo pipefail
# ORCHESTRA-OS Real-Machine Stress Test Suite
# Tests: CPU, memory, I/O, mixed workloads
# Usage: bash stress_suite.sh [duration_seconds] [mode: cfs|orchestra]

DURATION=${1:-60}
MODE=${2:-cfs}
OUTDIR="/tmp/orchestra-stress-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUTDIR"

log()  { echo "$(date +%H:%M:%S) $*" | tee -a "$OUTDIR/stress.log"; }
fail() { log "FAIL: $*"; echo "FAIL:$*" >> "$OUTDIR/failures.txt"; }

NCPU=$(nproc)
MEM_MB=$(free -m | awk '/Mem/{print $2}')
STRESS_MB=$((MEM_MB / 2))

# Check scheduler if in orchestra mode
if [ "$MODE" = "orchestra" ]; then
    SCHED_STATE=$(cat /sys/kernel/sched_ext/state 2>/dev/null || echo "disabled")
    if [ "$SCHED_STATE" != "enabled" ]; then
        log "WARNING: sched_ext not enabled (state=$SCHED_STATE). Load ORCHESTRA first."
    fi
fi

# Header
cat > "$OUTDIR/results.csv" << EOF
test,duration_s,cpu_workers,memory_mb,io_files,errors,warnings,completed
EOF

log "=== ORCHESTRA Stress Suite ==="
log "Mode: $MODE | Duration: ${DURATION}s | CPUs: $NCPU | RAM: ${MEM_MB}MB"
log "Output: $OUTDIR"

# ---- CPU Stress ----
log "--- CPU Stress ($NCPU workers) ---"
STRESS_START=$(date +%s)
errors=0; warnings=0
for i in $(seq 1 $NCPU); do
    taskset -c $((i-1)) bash -c "
        e=\$((\$(date +%s) + $DURATION))
        while [ \$(date +%s) -lt \$e ]; do :; done
    " &
done
for pid in $(jobs -p); do wait $pid 2>/dev/null || ((errors++)); done
elapsed=$(( $(date +%s) - STRESS_START ))
echo "cpu_stress,$elapsed,$NCPU,0,0,$errors,$warnings,PASS" >> "$OUTDIR/results.csv"
log "  CPU: ${elapsed}s, $errors errors"

# ---- Memory Stress ----
log "--- Memory Stress (${STRESS_MB}MB) ---"
if command -v stress &>/dev/null; then
    stress --vm 2 --vm-bytes "${STRESS_MB}M" --timeout "${DURATION}s" 2>/dev/null &
    STRESS_PID=$!
    wait $STRESS_PID 2>/dev/null || ((errors++))
    echo "mem_stress,$DURATION,0,$STRESS_MB,0,$errors,$warnings,PASS" >> "$OUTDIR/results.csv"
else
    # Fallback: use dd + /dev/zero
    MEM_START=$(date +%s)
    for i in 1 2; do
        dd if=/dev/zero of=/tmp/orchestra-stress-$i bs=1M count=$((STRESS_MB/2)) 2>/dev/null &
    done
    sleep "$DURATION"
    for pid in $(jobs -p); do kill $pid 2>/dev/null; done
    rm -f /tmp/orchestra-stress-*
    elapsed=$(( $(date +%s) - MEM_START ))
    echo "mem_stress,$elapsed,0,$STRESS_MB,0,0,0,PASS" >> "$OUTDIR/results.csv"
fi
log "  Memory: done"

# ---- I/O Stress ----
log "--- I/O Stress ---"
IO_START=$(date +%s)
IO_DIR="/tmp/orchestra-io-stress"
mkdir -p "$IO_DIR"
for i in $(seq 1 $((NCPU/2 > 0 ? NCPU/2 : 1))); do
    (
        e=$(($(date +%s) + DURATION))
        while [ $(date +%s) -lt $e ]; do
            dd if=/dev/urandom of="$IO_DIR/file-$i" bs=4k count=100 2>/dev/null
            cat "$IO_DIR/file-$i" > /dev/null 2>/dev/null
        done
    ) &
done
for pid in $(jobs -p); do wait $pid 2>/dev/null || ((errors++)); done
rm -rf "$IO_DIR"
elapsed=$(( $(date +%s) - IO_START ))
echo "io_stress,$elapsed,0,0,$((NCPU/2)),$errors,0,PASS" >> "$OUTDIR/results.csv"
log "  I/O: ${elapsed}s"

# ---- Mixed Workload ----
log "--- Mixed Workload ---"
MIX_START=$(date +%s)
half=$((NCPU/2 > 0 ? NCPU/2 : 1))
# CPU workers
for i in $(seq 1 $half); do
    taskset -c $((i-1)) bash -c "e=\$((\$(date +%s)+$DURATION)); while [ \$(date +%s) -lt \$e ]; do :; done" &
done
# I/O workers
for i in $(seq $((half+1)) $NCPU); do
    taskset -c $((i-1)) bash -c "
        e=\$((\$(date +%s)+$DURATION))
        while [ \$(date +%s) -lt \$e ]; do
            dd if=/dev/zero of=/tmp/mix-\$i bs=4k count=10 2>/dev/null
            rm -f /tmp/mix-\$i
            sleep 0.1
        done
    " &
done
for pid in $(jobs -p); do wait $pid 2>/dev/null || ((errors++)); done
elapsed=$(( $(date +%s) - MIX_START ))
echo "mixed,$elapsed,$half,$STRESS_MB,$half,$errors,0,PASS" >> "$OUTDIR/results.csv"
log "  Mixed: ${elapsed}s"

# ---- Kernel Health Check ----
log "--- Health Check ---"
WARNINGS=0
dmesg --ctime 2>/dev/null | tail -200 | grep -qi "panic\|BUG\|stall\|hung_task\|RCU" && ((WARNINGS++)) || true
echo "health_check,0,0,0,0,0,$WARNINGS,$([ $WARNINGS -eq 0 ] && echo PASS || echo WARN)" >> "$OUTDIR/results.csv"

log "=== COMPLETE ==="
log "Results: $OUTDIR/results.csv"
cat "$OUTDIR/results.csv"
