#!/bin/bash
# P0 ownership + action retest (known_recommand_fix.md).
# Claim class: VirtualBox / kernel-prototyped. Duration ~1 min.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCHED_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
KSRC="${ORCHESTRA_KERNEL_SRC:-$HOME/src/linux-v6.12.96}"
EVIDENCE_DIR="${1:-/tmp/p0-ownership-$(date +%Y%m%d-%H%M%S)}"
BRIDGE="$SCHED_DIR/bridge/orchestra_bridge"
WORK="$SCHED_DIR/scripts/fixed_work"
FAILS=0

mkdir -p "$EVIDENCE_DIR"
: > "$EVIDENCE_DIR/failures.txt"
: > "$EVIDENCE_DIR/run.log"
log() { echo "$(date +%H:%M:%S) $*"; echo "$(date +%H:%M:%S) $*" >> "$EVIDENCE_DIR/run.log"; }
fail() { log "FAIL: $*"; FAILS=$((FAILS+1)); echo "FAIL:$*" >> "$EVIDENCE_DIR/failures.txt"; }
pass() { log "PASS: $*"; }

tel_field() {
    local f="$1"
    sudo bpftool map dump name bridge_telemetr 2>/dev/null | python3 -c "
import sys, json
d=json.load(sys.stdin)[0]['value']
print(d.get('$f', 0))
" 2>/dev/null || echo 0
}

unload_sched() {
    sudo bash -c 'rm -rf /sys/fs/bpf/*' 2>/dev/null || true
    for l in $(sudo bpftool link list 2>&1 | grep struct_ops | awk -F: '{print $1}'); do
        sudo bpftool link detach id "$l" 2>/dev/null || true
    done
    sleep 1
}

log "=== Environment ==="
{
    echo "timestamp: $(date -Iseconds)"
    echo "hostname: $(hostname)"
    echo "kernel: $(uname -r)"
    echo "cpus: $(nproc)"
    echo "sched_ext: $(cat /sys/kernel/sched_ext/state 2>/dev/null || echo missing)"
} | tee "$EVIDENCE_DIR/environment.txt"

log "=== Build ==="
cd "$SCHED_DIR"
cc -O2 -Wall -Wextra -o "$WORK" "$SCRIPT_DIR/fixed_work.c"
clang -O2 -target bpf -g -nostdinc -D__BPF__ \
  -I include -I "$KSRC/tools/lib" -I "$KSRC/tools/bpf/bpftool/libbpf" \
  -I "$KSRC/include" -I "$KSRC/include/uapi" \
  -I "$KSRC/arch/x86/include" -I "$KSRC/arch/x86/include/generated" \
  -I "$KSRC/tools/sched_ext/include" -I /usr/include/bpf \
  -Wno-missing-declarations -Wno-visibility -Wno-address-of-packed-member \
  -c orchestra_scx_stage7.bpf.c -o orchestra_scx_stage7.bpf.o
cc -O2 -Wall -Wextra -I include bridge/orchestra_bridge.c \
  -o bridge/orchestra_bridge -lbpf
sha256sum orchestra_scx_stage7.bpf.o bridge/orchestra_bridge "$WORK" \
  > "$EVIDENCE_DIR/build_hashes.txt"

log "=== Load + pin ==="
unload_sched
sudo bpftool struct_ops register "$SCHED_DIR/orchestra_scx_stage7.bpf.o" \
  /sys/fs/bpf/orch_p0
sleep 2
S=$(cat /sys/kernel/sched_ext/state)
[[ "$S" == "enabled" ]] || fail "sched-load: state=$S"
sudo "$BRIDGE" --pin-maps
sudo "$BRIDGE" --status | tee "$EVIDENCE_DIR/status_after_load.txt"

log "=== Negative: no opt-in (enqueue must stay 0 while idle_dispatch may rise) ==="
ENQ0=$(tel_field enqueue_count)
RUN0=$(tel_field running_count)
IDL0=$(tel_field idle_dispatch_count)
"$WORK" 20000000 &
NPID=$!
sleep 1
kill "$NPID" 2>/dev/null || true
wait "$NPID" 2>/dev/null || true
ENQ1=$(tel_field enqueue_count)
RUN1=$(tel_field running_count)
IDL1=$(tel_field idle_dispatch_count)
log "no-optin enqueue $ENQ0->$ENQ1 running $RUN0->$RUN1 idle_disp $IDL0->$IDL1"
if [ "$ENQ1" -gt "$ENQ0" ]; then
    fail "enqueue rose without SCHED_EXT opt-in (unexpected under SWITCH_PARTIAL)"
else
    pass "partial switch: CFS worker did not enter enqueue"
fi

log "=== Ownership: opt-in worker ==="
"$WORK" 400000000 &
WPID=$!
sleep 0.2
sudo "$BRIDGE" --opt-in --target-pid "$WPID"
sudo "$BRIDGE" --publish --action RUN --target-pid "$WPID"
sleep 3
ENQ=$(tel_field enqueue_count)
RUNC=$(tel_field run_count)
RUNNING=$(tel_field running_count)
ENABLE=$(tel_field task_enable_count)
FAST=$(tel_field fastpath_run_count)
log "owned enqueue=$ENQ run=$RUNC running=$RUNNING enable=$ENABLE fastpath=$FAST"
{
    echo "enqueue_count=$ENQ"
    echo "run_count=$RUNC"
    echo "running_count=$RUNNING"
    echo "task_enable_count=$ENABLE"
    echo "fastpath_run_count=$FAST"
} > "$EVIDENCE_DIR/ownership.txt"
if [ "$ENQ" -gt 0 ] && [ "$RUNNING" -gt 0 ] && [ "$ENABLE" -gt 0 ]; then
    pass "ownership gate (enqueue>0 running>0 enable>0)"
else
    fail "ownership gate: enqueue=$ENQ running=$RUNNING enable=$ENABLE"
fi
kill "$WPID" 2>/dev/null || true
wait "$WPID" 2>/dev/null || true

log "=== MIGRATE targeting ==="
"$WORK" 200000000 &
MPID=$!
sleep 0.2
sudo "$BRIDGE" --opt-in --target-pid "$MPID"
TCPU=$(( $(nproc) > 1 ? 1 : 0 ))
sudo "$BRIDGE" --publish --action MIGRATE --target-pid "$MPID" --target-cpu "$TCPU"
sleep 2
MIG_R=$(tel_field migrate_requested)
MIG_E=$(tel_field migrate_effective)
log "migrate requested=$MIG_R effective=$MIG_E target_cpu=$TCPU"
echo "migrate_requested=$MIG_R migrate_effective=$MIG_E" > "$EVIDENCE_DIR/migrate.txt"
if [ "$MIG_R" -gt 0 ]; then
    pass "MIGRATE requested on owned task"
else
    fail "MIGRATE telemetry stayed 0"
fi
kill "$MPID" 2>/dev/null || true
wait "$MPID" 2>/dev/null || true

log "=== Completion-time (owned vs CFS) ==="
cfs_ms() {
    local s e
    s=$(date +%s%N)
    "$WORK" 80000000
    e=$(date +%s%N)
    echo $(( (e - s) / 1000000 ))
}
CFS_MS=$(cfs_ms)
"$WORK" 80000000 &
CPID=$!
sleep 0.05
sudo "$BRIDGE" --opt-in --target-pid "$CPID" || true
sudo "$BRIDGE" --publish --action RUN --target-pid "$CPID" || true
s=$(date +%s%N)
wait "$CPID" 2>/dev/null || true
e=$(date +%s%N)
ORCH_MS=$(( (e - s) / 1000000 ))
log "completion CFS=${CFS_MS}ms ORCHESTRA_owned=${ORCH_MS}ms (VirtualBox, n=1)"
echo "cfs_ms=$CFS_MS orchestra_ms=$ORCH_MS" > "$EVIDENCE_DIR/completion.txt"

unload_sched
log "=== COMPLETE fails=$FAILS evidence=$EVIDENCE_DIR ==="
echo "$FAILS" > "$EVIDENCE_DIR/fail_count.txt"
[ "$FAILS" -eq 0 ]
