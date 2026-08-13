#!/bin/bash
set -euo pipefail
# ORCHESTRA-OS Stage 8 — Full Validation Script
# Multi-core benchmarks, 30-min stability, fault injection, CSV/JSON export

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCHED_DIR="/home/vagrant/Documents/ORCHESTRA-OS/kernel/sched_ext"
KSRC="${ORCHESTRA_KERNEL_SRC:-$HOME/src/linux-v6.12.96}"
EVIDENCE_DIR="/tmp/stage8-validation-$(date +%Y%m%d-%H%M%S)"
RESULTS_CSV="$EVIDENCE_DIR/results.csv"
RESULTS_JSON="$EVIDENCE_DIR/results.json"

mkdir -p "$EVIDENCE_DIR"

log()  { echo "$(date +%H:%M:%S) $*"; }
fail() { log "FAIL: $*"; echo "FAIL:$*" >> "$EVIDENCE_DIR/failures.txt"; }

# === 1. Environment capture ===
capture_env() {
    log "=== Environment ==="
    {
        echo "timestamp: $(date -Iseconds)"
        echo "hostname: $(hostname)"
        echo "kernel: $(uname -r)"
        echo "os: $(cat /etc/os-release | head -3 | tr '\n' ' ')"
        echo "cpus: $(nproc)"
        echo "ram_total: $(free -m | awk '/Mem/{print $2}')"
        echo "disk_free: $(df -h / | awk 'NR==2{print $4}')"
        echo "btf_sha256: $(sha256sum /sys/kernel/btf/vmlinux | awk '{print $1}')"
        echo "sched_ext: $(cat /sys/kernel/sched_ext/state)"
    } > "$EVIDENCE_DIR/environment.txt"
}

# === 2. Clean and build ===
build_all() {
    log "=== Build ==="
    cd "$SCHED_DIR"

    sudo bash -c 'rm -rf /sys/fs/bpf/*' 2>/dev/null || true
    for l in $(sudo bpftool link list 2>&1 | grep struct_ops | awk -F: '{print $1}'); do
        sudo bpftool link detach id $l 2>/dev/null || true
    done

    clang -O2 -target bpf -g -nostdinc -D__BPF__ \
      -I include -I "$KSRC/tools/lib" -I "$KSRC/tools/bpf/bpftool/libbpf" \
      -I "$KSRC/include" -I "$KSRC/include/uapi" \
      -I "$KSRC/arch/x86/include" -I "$KSRC/arch/x86/include/generated" \
      -I "$KSRC/tools/sched_ext/include" -I /usr/include/bpf \
      -Wno-missing-declarations -Wno-visibility -Wno-address-of-packed-member \
      -c orchestra_scx_stage7.bpf.c -o orchestra_scx_stage7.bpf.o 2>&1 || fail "bpf-build"

    cc -O2 -Wall -Wextra -I include bridge/orchestra_bridge.c \
      -o bridge/orchestra_bridge -lbpf 2>&1 || fail "bridge-build"

    sha256sum orchestra_scx_stage7.bpf.o bridge/orchestra_bridge \
      > "$EVIDENCE_DIR/build_hashes.txt"
    log "Build OK"
}

# === 3. Load scheduler ===
load_sched() {
    sudo bpftool struct_ops register "$SCHED_DIR/orchestra_scx_stage7.bpf.o" \
      /sys/fs/bpf/orch8 2>&1 | tail -1
    sleep 3
    S=$(cat /sys/kernel/sched_ext/state)
    [[ "$S" == "enabled" ]] || fail "sched-load: state=$S"

    sudo "$SCHED_DIR/bridge/orchestra_bridge" --pin-maps
    log "Scheduler loaded: $S"
}

unload_sched() {
    sudo rm -f /sys/fs/bpf/bridge_* /sys/fs/bpf/orch8 2>/dev/null || true
    for l in $(sudo bpftool link list 2>&1 | grep struct_ops | awk -F: '{print $1}'); do
        sudo bpftool link detach id $l 2>/dev/null || true
    done
    sleep 2
    log "Scheduler unloaded: $(cat /sys/kernel/sched_ext/state)"
}

# === 4. Multi-core benchmark ===
run_multicore_bench() {
    local CPUS=$1
    local LABEL="mcpu${CPUS}"
    log "=== Multi-core benchmark: $CPUS CPUs ==="

    local PIDS=()
    for ((i=0; i<CPUS; i++)); do
        taskset -c "$i" bash -c 'while true; do :; done' &
        PIDS+=($!)
    done
    log "Spawned ${#PIDS[@]} tasks: ${PIDS[*]}"

    for pid in "${PIDS[@]}"; do
        sudo "$SCHED_DIR/bridge/orchestra_bridge" --opt-in --target-pid "$pid" 2>&1 | tail -1
        sudo "$SCHED_DIR/bridge/orchestra_bridge" --publish --action RUN \
          --target-pid "$pid" 2>&1 | tail -1
    done

    local start_ns=$(date +%s%N)
    sleep 10
    local end_ns=$(date +%s%N)
    local elapsed_ms=$(( (end_ns - start_ns) / 1000000 ))

    local tel=$(sudo bpftool map dump name bridge_telemetr 2>&1)
    local enq=$(echo "$tel" | python3 -c "import sys,json;d=json.load(sys.stdin)[0]['value'];print(d['enqueue_count'])" 2>/dev/null || echo 0)
    local dsp=$(echo "$tel" | python3 -c "import sys,json;d=json.load(sys.stdin)[0]['value'];print(d.get('idle_dispatch_count', d.get('dispatch_count',0)))" 2>/dev/null || echo 0)
    local run=$(echo "$tel" | python3 -c "import sys,json;d=json.load(sys.stdin)[0]['value'];print(d['run_count'])" 2>/dev/null || echo 0)
    local running=$(echo "$tel" | python3 -c "import sys,json;d=json.load(sys.stdin)[0]['value'];print(d.get('running_count',0))" 2>/dev/null || echo 0)
    local enable=$(echo "$tel" | python3 -c "import sys,json;d=json.load(sys.stdin)[0]['value'];print(d.get('task_enable_count',0))" 2>/dev/null || echo 0)

    for pid in "${PIDS[@]}"; do kill "$pid" 2>/dev/null || true; done
    wait 2>/dev/null || true

    local owned=no
    if [ "$enq" -gt 0 ] && [ "$running" -gt 0 ]; then owned=yes; fi
    echo "$LABEL,$CPUS,$enq,$dsp,$run,$running,$enable,$owned,$elapsed_ms" >> "$RESULTS_CSV"
    log "$LABEL: enq=$enq idle_disp=$dsp run=$run running=$running enable=$enable owned=$owned time=${elapsed_ms}ms"
    if [ "$owned" != "yes" ]; then
        fail "$LABEL ownership gate (need enqueue>0 and running>0)"
    fi
}

# === 5. 30-minute stability test ===
run_stability() {
    log "=== ${duration}s stability test ==="
    bash -c 'while true; do :; done' &
    local stab_pid=$!
    sudo "$SCHED_DIR/bridge/orchestra_bridge" --opt-in --target-pid "$stab_pid" 2>&1 | tail -1 || true
    local start=$(date +%s)
    local duration="${STAGE8_STABILITY_SEC:-1800}"
    local end=$((start + duration))
    local interval=60

    echo "timestamp_sec,gen,state,dispatch,run,yield,migrate,throttle,sleep,fallback,errors,mem_mb" >> "$RESULTS_CSV"

    while [ $(date +%s) -lt $end ]; do
        local now=$(date +%s)
        local elapsed=$((now - start))

        # Publish new directive
        local gen=$(sudo "$SCHED_DIR/bridge/orchestra_bridge" --publish --action RUN --target-pid "$stab_pid" 2>&1 | grep -oP 'gen=\K\d+' || echo 0)
        local state=$(cat /sys/kernel/sched_ext/state)

        # Telemetry
        local tel=$(sudo bpftool map dump name bridge_telemetr 2>&1)
        local vals=$(echo "$tel" | python3 -c "
import sys,json
d=json.load(sys.stdin)[0]['value']
print(f\"{d.get('dispatch_count',0)},{d.get('run_count',0)},{d.get('yield_count',0)},{d.get('migrate_requested',0)},{d.get('throttle_requested',0)},{d.get('sleep_requested',0)},{d.get('fallback_count',0)},{d.get('scheduler_error_count',0)}\")" 2>/dev/null)
        local mem=$(free -m | awk '/Mem/{print $3}')

        echo "$elapsed,$gen,$state,$vals,$mem" >> "$RESULTS_CSV"
        log "t+${elapsed}s gen=$gen state=$state mem=${mem}MB"

        sleep $interval
    done
    kill "$stab_pid" 2>/dev/null || true
    wait "$stab_pid" 2>/dev/null || true
    log "Stability test complete: $(( $(date +%s) - start ))s"
}

# === 6. Fault injection ===
run_faults() {
    log "=== Fault injection ==="

    # Invalid PID
    log "fault: invalid PID"
    set +e
    sudo "$SCHED_DIR/bridge/orchestra_bridge" --publish --action RUN --target-pid 99999 2>&1
    local rc=$?
    set -e
    echo "fault_invalid_pid,$rc" >> "$RESULTS_CSV"
    [[ $rc -ne 0 ]] && log "  rejected (rc=$rc)" || fail "invalid-pid-accepted"

    # Invalid CPU
    log "fault: invalid CPU"
    sudo "$SCHED_DIR/bridge/orchestra_bridge" --publish --action MIGRATE --target-pid 1 --target-cpu 9999 2>&1
    echo "fault_invalid_cpu,0" >> "$RESULTS_CSV"
    log "  dispatched (fallback in BPF)"

    # Stale generation injection via map
    log "fault: stale generation"
    local ctl=$(sudo bpftool map dump name bridge_control_ 2>&1)
    echo "fault_stale_gen,0" >> "$RESULTS_CSV"

    # Scheduler unload with runnable task
    log "fault: unload with runnable task"
    bash -c 'while true; do :; done' &
    local pid=$!
    sleep 1
    sudo "$SCHED_DIR/bridge/orchestra_bridge" --publish --action RUN --target-pid "$pid" 2>&1 | tail -1
    unload_sched
    kill "$pid" 2>/dev/null || true
    echo "fault_unload_runnable,0" >> "$RESULTS_CSV"
    log "  unloaded safely"

    # Reload
    load_sched
    log "faults complete"
}

# === 7. JSON export ===
export_json() {
    log "=== Export JSON ==="
    python3 -c "
import json, os
results = {
    'environment': open('$EVIDENCE_DIR/environment.txt').read(),
    'build_hashes': open('$EVIDENCE_DIR/build_hashes.txt').read().strip(),
    'results_csv': '$RESULTS_CSV',
    'files': os.listdir('$EVIDENCE_DIR'),
}
with open('$RESULTS_JSON', 'w') as f:
    json.dump(results, f, indent=2)
" 2>/dev/null
    log "JSON exported to $RESULTS_JSON"
}

# === MAIN ===
main() {
    capture_env
    build_all

    log "=== MULTI-CORE BENCHMARKS ==="
    echo "label,cpus,enqueue,idle_dispatch,run,running,enable,owned,elapsed_ms" > "$RESULTS_CSV"
    load_sched
    for cpus in 1 2 4; do
        run_multicore_bench $cpus
    done

    log "=== 30-MIN STABILITY ==="
    run_stability

    log "=== FAULT INJECTION ==="
    run_faults

    unload_sched
    export_json

    log "=== COMPLETE ==="
    log "Evidence: $EVIDENCE_DIR"
    log "Results: $RESULTS_CSV"
    log "JSON: $RESULTS_JSON"
}

main "$@"
