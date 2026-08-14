#!/usr/bin/env python3
"""Source-level regressions for safety properties that need runtime proof later."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BPF = (ROOT / "kernel/sched_ext/orchestra_scx_stage7.bpf.c").read_text()
COMPAT_BPF = (ROOT / "kernel/sched_ext/orchestra_scx.bpf.c").read_text()
ABI = (ROOT / "kernel/sched_ext/include/orchestra_bridge_v1.h").read_text()
BRIDGE = (ROOT / "kernel/sched_ext/bridge/orchestra_bridge.c").read_text()
LOADER = (ROOT / "kernel/sched_ext/bridge/orchestra_loader.c").read_text()
LEGACY_LOADER = (ROOT / "kernel/sched_ext/orchestra_scx.c").read_text()
ENGINE = (ROOT / "orchestra_paper_cpu_demo/orchestra_paper_cpu.c").read_text()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    require("SCX_OPS_SWITCH_PARTIAL" not in BPF,
            "partial-switch starvation mode must not return")
    require('include "orchestra_scx_stage7.bpf.c"' in COMPAT_BPF,
            "the historical BPF filename must build the canonical scheduler")
    require("syscall(" not in LEGACY_LOADER,
            "the retired loader must not change task policy")
    require("dir_cache" not in BPF,
            "cross-CPU mutable directive cache must not return")
    require("BPF_MAP_TYPE_HASH" in BPF and "orch_directives" in BPF,
            "directives must remain per-task hash entries")
    require("start_boottime_ns" in BPF and "p->start_boottime" in BPF,
            "task lifetime identity must remain enforced")
    require("bpf_spin_lock(&dir->lock)" in BPF,
            "directive snapshot must remain lock coherent")
    require("control_snapshot_equal" in BPF and "attempt < 2" in BPF,
            "control/directive publication must retain bounded validation")
    require("BRIDGE_DEFERRED_DSQ" in BPF and "deferred_timerfn" in BPF,
            "SLEEP/THROTTLE deferred eligibility must remain implemented")
    require("deferred_timer_tick_count" in BPF and
            "deferred_release_failure_count" in BPF,
            "deferred progress diagnostics must remain observable")
    require("BRIDGE_DEFER_MAP_NAME" in ABI and
            '"--defer-timer-map-id"' in BRIDGE,
            "the deferred timer map must remain in the exact pin contract")
    require(LOADER.index("bpf_map__pin") <
            LOADER.index("bpf_map__attach_struct_ops"),
            "the loader must pin maps before struct_ops attach initializes timers")
    require("deferred timer map was not pinned before attach" in BRIDGE,
            "late bridge pinning must not accept an already-cancelled timer")
    require("throttle_budget_ns" in BPF and "runtime_used_ns" in BPF,
            "THROTTLE must retain runtime budget accounting")
    require("struct bridge_task_state {\n    ORCHESTRA_MAP_LOCK lock" in ABI and
            "bpf_spin_lock(&state->lock)" in BPF,
            "per-task timer/callback state must remain synchronized")
    require("bpf_cpumask_test_cpu(cpu, p->cpus_ptr)" in BPF and
            "scx_bpf_get_online_cpumask" in BPF,
            "MIGRATE must check affinity and online masks")
    require("SCX_DSQ_LOCAL_ON | dir->target_cpu" in BPF,
            "MIGRATE re-enqueues must retain their validated target CPU")
    require("SCX_OPS_KEEP_BUILTIN_IDLE" in BPF,
            "built-in idle tracking must remain enabled")
    require("scx_bpf_consume(SCX_DSQ_GLOBAL)" not in BPF,
            "dispatch must not consume the reserved global DSQ")
    require("migrate_running_target_count" in BPF and "actual_cpu" in BPF,
            "migration telemetry must correlate requested and observed CPUs")
    require("select_cpu_direct_insert_count" in ABI and
            "enqueue_callback_count" in ABI,
            "callback/direct-insertion telemetry must remain unambiguous")
    require("last_generation = 0" in BPF and
            "Never reset last_generation" in BRIDGE,
            "generation may initialize only at a new scheduler epoch")
    require("bpf_map_get_next_id" not in BRIDGE,
            "global prefix map discovery must not return")
    require("info.value_size != spec->value_size" in BRIDGE,
            "bridge map schema validation must remain exact")
    require("ORCHESTRA_ACTION_SLEEP = 1" in
            (ROOT / "kernel/sched_ext/include/orchestra_abi.h").read_text(),
            "canonical/wire action ABI drift")
    require("sizeof(struct orchestra_task_identity) == 16" in ABI,
            "shared task identity size assertion missing")
    require("canonical_action_to_wire" in ENGINE and
            "typedef enum orchestra_action_id action_t" in ENGINE,
            "canonical engine-to-wire action translation must remain explicit")
    require("m.s3 = m.s3_conditioned" in ENGINE and
            "if (m.s4_burst < m.s4) m.s4 = m.s4_burst" in ENGINE,
            "corrected conditioned-S3/burst-S4 semantics must remain canonical")
    require("calibrated_prediction_confidence" in ENGINE and
            "calibrate_fixed_gain" in ENGINE and "kalman" not in ENGINE.lower(),
            "offline fixed-gain predictor must not regress to adaptive Kalman")
    print("PASS sched_ext source safety invariants")


if __name__ == "__main__":
    main()
