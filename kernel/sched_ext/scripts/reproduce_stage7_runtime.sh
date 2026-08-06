#!/bin/bash
# ORCHESTRA-OS Stage 7 — Runtime Evidence Reproduction Script
# Runs all action tests with bounded timeouts and safe fallbacks.
set -euo pipefail

KSRC="${ORCHESTRA_KERNEL_SRC:-$HOME/src/linux-v6.12.96}"
SCHED_DIR="$HOME/Documents/ORCHESTRA-OS/kernel/sched_ext"
EVIDENCE_DIR="/tmp/stage7-evidence-$(date +%Y%m%d-%H%M%S)"
DISPOSABLE_PID=""

cleanup() {
    echo "=== CLEANUP ==="
    sudo rm -f /sys/fs/bpf/bridge_* /sys/fs/bpf/orch7* 2>/dev/null || true
    local lids=$(sudo bpftool link list 2>&1 | grep struct_ops | awk -F: '{print $1}' | tr -d ' ')
    for l in $lids; do sudo bpftool link detach id $l 2>/dev/null || true; done
    sleep 1
}

log() { echo "$(date +%H:%M:%S) $*" | tee -a "$EVIDENCE_DIR/log.txt"; }
ok()  { log "PASS: $*"; }
fail() { log "FAIL: $*"; exit 1; }

mkdir -p "$EVIDENCE_DIR"
log "Stage 7 evidence campaign starting"
log "Evidence dir: $EVIDENCE_DIR"

# === 1. Environment ===
log "--- Environment ---"
uname -a | tee "$EVIDENCE_DIR/uname.txt"
cat /sys/kernel/sched_ext/state | tee "$EVIDENCE_DIR/sched_ext_state_pre.txt"
sha256sum /sys/kernel/btf/vmlinux | tee "$EVIDENCE_DIR/btf_hash.txt"
head -5 "$KSRC/Makefile" | tee "$EVIDENCE_DIR/kernel_source.txt"

# === 2. Clean and build ===
log "--- Build ---"
cleanup
cd "$SCHED_DIR"

sudo bpftool btf dump file /sys/kernel/btf/vmlinux format c > include/vmlinux.h 2>/dev/null

clang -O2 -target bpf -g -nostdinc -D__BPF__ \
  -I include -I "$KSRC/tools/lib" -I "$KSRC/tools/bpf/bpftool/libbpf" \
  -I "$KSRC/include" -I "$KSRC/include/uapi" \
  -I "$KSRC/arch/x86/include" -I "$KSRC/arch/x86/include/generated" \
  -I "$KSRC/tools/sched_ext/include" -I /usr/include/bpf \
  -Wno-missing-declarations -Wno-visibility -Wno-address-of-packed-member \
  -c orchestra_scx_stage7.bpf.c -o orchestra_scx_stage7.bpf.o 2>&1 || fail "BPF build"

cc -O2 -Wall -Wextra -I include bridge/orchestra_bridge.c -o bridge/orchestra_bridge -lbpf 2>&1 || fail "Bridge build"

sha256sum orchestra_scx_stage7.bpf.o bridge/orchestra_bridge include/vmlinux.h > "$EVIDENCE_DIR/artifacts.sha256"

# === 3. Official scx_simple ===
log "--- scx_simple 3 cycles ---"
for i in 1 2 3; do
    timeout --signal=INT --kill-after=3s 10s sudo /usr/bin/scx_simple 2>&1 | tail -1 | tee -a "$EVIDENCE_DIR/scx_simple_$i.log"
    S=$(cat /sys/kernel/sched_ext/state)
    [ "$S" = "disabled" ] || fail "scx_simple cycle $i: state=$S"
    ok "scx_simple cycle $i"
done

# === 4. Load Stage 7 ===
log "--- Load ORCHESTRA Stage 7 ---"
cleanup
sudo bpftool struct_ops register orchestra_scx_stage7.bpf.o /sys/fs/bpf/orch7 2>&1 | tee /dev/stderr | tail -2 > "$EVIDENCE_DIR/attach.log"
sleep 3
S=$(cat /sys/kernel/sched_ext/state)
[ "$S" = "enabled" ] || fail "attach: state=$S"
ok "scheduler enabled: $S"

# Pin maps
for m in bridge_control_ bridge_directiv bridge_telemetr bridge_task_map; do
    ID=$(sudo bpftool map list 2>&1 | grep -m1 "name $m" | awk '{print $1}' | tr -d ':')
    [ -n "$ID" ] && sudo bpftool map pin id $ID "/sys/fs/bpf/$m" 2>/dev/null || true
done

# === 5. Bridge status ===
log "--- Bridge status ---"
sudo "$SCHED_DIR/bridge/orchestra_bridge" --status 2>&1 | tee "$EVIDENCE_DIR/bridge_status.txt"
grep -q "0x4f524342" "$EVIDENCE_DIR/bridge_status.txt" || fail "bridge magic mismatch"
ok "bridge status"

# === 6. Dry-run ===
log "--- Dry-run ---"
GEN_BEFORE=$(sudo bpftool map dump name bridge_control_ 2>&1 | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['value']['published_generation'])" 2>/dev/null || echo "0")
sudo "$SCHED_DIR/bridge/orchestra_bridge" --publish --action RUN --target-pid 1 --dry-run 2>&1 | tee "$EVIDENCE_DIR/dry_run.log"
GEN_AFTER=$(sudo bpftool map dump name bridge_control_ 2>&1 | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['value']['published_generation'])" 2>/dev/null || echo "0")
[ "$GEN_BEFORE" = "$GEN_AFTER" ] || fail "dry-run mutated generation: $GEN_BEFORE → $GEN_AFTER"
ok "dry-run: gen unchanged ($GEN_BEFORE)"

# === 7. Publish generations 1-6 ===
log "--- Publish gen 1-6 ---"
for i in 1 2 3 4 5 6; do
    OUT=$(sudo "$SCHED_DIR/bridge/orchestra_bridge" --publish --action RUN --target-pid 1 2>&1)
    echo "$OUT" | tee -a "$EVIDENCE_DIR/publish.log"
    echo "$OUT" | grep -q "published gen=$i" || fail "gen $i publish mismatch: $OUT"
done
ok "published generations 1-6"

# === 8. Invalid PID rejection ===
log "--- Invalid PID ---"
sudo "$SCHED_DIR/bridge/orchestra_bridge" --publish --action RUN --target-pid 99999 2>&1; RC=$?
[ $RC -eq 6 ] || fail "invalid PID exit: $RC (expected 6)"
ok "invalid PID rejected (exit 6)"

# === 9. Adaptive slice tests ===
log "--- Adaptive slices ---"
for SLICE in 0 250000 500000 1000000 5000000 100000000 200000000; do
    sudo "$SCHED_DIR/bridge/orchestra_bridge" --publish --action RUN --target-pid 1 --slice-ns $SLICE --dry-run 2>&1 | tee -a "$EVIDENCE_DIR/adaptive_slice.log"
done
ok "adaptive slice dry-runs complete"

# === 10. Task cleanup ===
DISPOSABLE_PID=""
log "=== Spawn disposable test task ==="
# Start a background CPU-burning task
(
    while true; do
        volatile double x=1.0; for i in $(seq 1 1000); do x=x*1.000001+0.000001; done
    done
) &
DISPOSABLE_PID=$!
sleep 1
log "Disposable task PID=$DISPOSABLE_PID"

# === 11. RUN test ===
log "--- RUN test ---"
sudo "$SCHED_DIR/bridge/orchestra_bridge" --publish --action RUN --target-pid "$DISPOSABLE_PID" 2>&1 | tee "$EVIDENCE_DIR/run_test.log"
sleep 2
sudo bpftool map dump name bridge_telemetr 2>&1 | tee "$EVIDENCE_DIR/telemetry_after_run.txt" | head -25
ok "RUN test dispatched"

# === 12. YIELD test ===
log "--- YIELD test ---"
sudo "$SCHED_DIR/bridge/orchestra_bridge" --publish --action YIELD --target-pid "$DISPOSABLE_PID" 2>&1 | tee "$EVIDENCE_DIR/yield_test.log"
sleep 2
ok "YIELD test dispatched"

# === 13. MIGRATE test ===
log "--- MIGRATE test ---"
sudo "$SCHED_DIR/bridge/orchestra_bridge" --publish --action MIGRATE --target-pid "$DISPOSABLE_PID" --target-cpu 0 2>&1 | tee "$EVIDENCE_DIR/migrate_test.log"
# Invalid CPU test
sudo "$SCHED_DIR/bridge/orchestra_bridge" --publish --action MIGRATE --target-pid "$DISPOSABLE_PID" --target-cpu 9999 2>&1 | tee -a "$EVIDENCE_DIR/migrate_test.log" || true
ok "MIGRATE tests dispatched"

# === 14. THROTTLE test ===
log "--- THROTTLE test ---"
sudo "$SCHED_DIR/bridge/orchestra_bridge" --publish --action THROTTLE --target-pid "$DISPOSABLE_PID" --slice-ns 500000 --throttle-interval-ns 50000000 2>&1 | tee "$EVIDENCE_DIR/throttle_test.log"
ok "THROTTLE test dispatched"

# === 15. SLEEP test ===
log "--- SLEEP test ---"
sudo "$SCHED_DIR/bridge/orchestra_bridge" --publish --action SLEEP --target-pid "$DISPOSABLE_PID" --not-before-ns $(( $(date +%s) * 1000000000 + 2000000000 )) 2>&1 | tee "$EVIDENCE_DIR/sleep_test.log"
ok "SLEEP test dispatched"

# === 16. Kill disposable ===
log "--- Kill disposable task ---"
kill "$DISPOSABLE_PID" 2>/dev/null || true
wait "$DISPOSABLE_PID" 2>/dev/null || true
ok "task cleanup"

# === 17. Telemetry dump ===
log "--- Final telemetry ---"
sudo bpftool map dump name bridge_telemetr 2>&1 | tee "$EVIDENCE_DIR/telemetry_final.txt"
sudo bpftool map dump name bridge_control_ 2>&1 | tee "$EVIDENCE_DIR/control_final.txt"

# === 18. Clean unload ===
log "--- Unload ---"
sudo rm -f /sys/fs/bpf/bridge_* 2>/dev/null || true
LIDS=$(sudo bpftool link list 2>&1 | grep struct_ops | awk -F: '{print $1}' | tr -d ' ')
for l in $LIDS; do sudo bpftool link detach id $l 2>/dev/null || true; done
sleep 2
S=$(cat /sys/kernel/sched_ext/state)
[ "$S" = "disabled" ] || fail "unload: state=$S"
ok "scheduler disabled: $S"

# === 19. Kernel logs ===
log "--- Kernel logs ---"
sudo dmesg --ctime 2>/dev/null | tail -100 > "$EVIDENCE_DIR/dmesg_tail.txt"
sudo dmesg --ctime 2>/dev/null | grep -c "stage7.*enabled" > "$EVIDENCE_DIR/enable_count.txt" || true
echo "enable_count=$(cat $EVIDENCE_DIR/enable_count.txt)"

log "=== Stage 7 evidence campaign COMPLETE ==="
log "Evidence: $EVIDENCE_DIR"
ok "ALL GATES PASSED"
