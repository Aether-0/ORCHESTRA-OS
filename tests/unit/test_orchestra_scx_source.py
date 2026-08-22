#!/usr/bin/env python3
"""Source-level regressions for safety properties that need runtime proof later."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BPF = (ROOT / "kernel/sched_ext/orchestra_scx_stage7.bpf.c").read_text()
COMPAT_BPF = (ROOT / "kernel/sched_ext/orchestra_scx.bpf.c").read_text()
ABI = (ROOT / "kernel/sched_ext/include/orchestra_bridge_v1.h").read_text()
KERNEL_V8 = (ROOT / "kernel/sched_ext/include/orchestra_kernel_v8.h").read_text()
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
    require("retire_released_sleep_directive" in BPF and
            "dir->action = ORCHESTRA_ACTION_RUN" in BPF and
            "dir->generation == generation" in BPF,
            "released SLEEP generations must retire without overwriting newer directives")
    require("deferred_timer_tick_count" in BPF and
            "deferred_release_failure_count" in BPF,
            "deferred progress diagnostics must remain observable")
    require("BRIDGE_DEFER_MAP_NAME" in ABI and
            '"--defer-timer-map-id"' in BRIDGE,
            "the deferred timer map must remain in the exact pin contract")
    require("BRIDGE_SIGNAL_MAP_NAME" in ABI and
            "orch_signal" in BPF and "struct bridge_signal_frame" in BRIDGE,
            "the fixed-point kernel signal frame map must remain in the ABI")
    require("BRIDGE_DIRECTIVE_F_REQUIRE_SIGNAL" in BPF and
            "snapshot_signal" in BPF and "signal_is_valid" in BPF and
            "--signal-publish" in BRIDGE and
            "BRIDGE_STREAM_F_PUBLISH_SIGNAL" in BRIDGE and
            "BRIDGE_STREAM_F_REQUIRE_SIGNAL" in BRIDGE,
            "signal-required directives must have bounded kernel freshness validation")
    require("signal_permille" in ENGINE and
            "signal_sequence" in ENGINE and
            "publish_signal" in ENGINE and
            "require_signal" in ENGINE,
            "the userspace kernel bridge must publish and require the fixed-point signal")
    require("scheduling_policy_is_rt" in BRIDGE and
            "sched_getscheduler" in BRIDGE and
            "refusing adaptive directive for RT policy" in BRIDGE,
            "bridge directives must fail closed for RT scheduling policies")
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
    require("struct orchestra_task_identity target_identity" in BRIDGE and
            "memcmp(&next, &target_identity, sizeof(next)) == 0" in BRIDGE,
            "targeted status must filter the full live task identity")
    require("ORCHESTRA_ACTION_SLEEP = 1" in
            (ROOT / "kernel/sched_ext/include/orchestra_abi.h").read_text(),
            "canonical/wire action ABI drift")
    require("sizeof(struct orchestra_task_identity) == 16" in ABI and
            "sizeof(struct bridge_signal_frame) == 152" in ABI and
            "sizeof(struct bridge_stream_request) == 176" in ABI,
            "shared task identity size assertion missing")
    require("canonical_action_to_wire" in ENGINE and
            "typedef enum orchestra_action_id action_t" in ENGINE,
            "canonical engine-to-wire action translation must remain explicit")
    require("ORCHESTRA_KERNEL_ABI_VERSION             8u" in KERNEL_V8 and
            "ORCHESTRA_KERNEL_STATE_SCHEMA_VERSION" in KERNEL_V8 and
            "ORCHESTRA_KERNEL_POLICY_SCHEMA_VERSION" in KERNEL_V8,
            "kernel adaptive ABI/schema versions must be explicit")
    require("ORCHESTRA_KERNEL_POLICY_BANK_COUNT       2u" in KERNEL_V8 and
            "ORCHESTRA_KERNEL_MAX_POLICY_STATES" in KERNEL_V8 and
            "active_bank" in KERNEL_V8 and "policy_generation" in KERNEL_V8,
            "policy publication must use bounded double-buffer generation state")
    require("struct orchestra_runtime_state_v8" in KERNEL_V8 and
            "prediction_generation" in KERNEL_V8 and
            "prediction_expires_ns" in KERNEL_V8 and
            "s1_permille" in KERNEL_V8 and "q_permille" in KERNEL_V8,
            "runtime/prediction/coordination state contract missing")
    require("struct orchestra_task_hot_v8" in KERNEL_V8 and
            "struct orchestra_task_diag_v8" in KERNEL_V8 and
            "controller_override_action" in KERNEL_V8 and
            "throttle_deadline_ns" in KERNEL_V8,
            "hot and diagnostic per-task adaptive state missing")
    require("ORCHESTRA_KERNEL_CAP_ADAPTIVE_SLICE" in KERNEL_V8 and
            "ORCHESTRA_KERNEL_CAP_STATE_CPU_SELECTION" in KERNEL_V8 and
            "ORCHESTRA_KERNEL_CAP_SLEEP_DEFER_COMPAT" in KERNEL_V8 and
            "ORCHESTRA_KERNEL_CAP_THROTTLE_DEFER_COMPAT" in KERNEL_V8 and
            "ORCHESTRA_MIGRATE_V8_ALREADY_LOCAL" in KERNEL_V8,
            "v8 action backend capabilities/outcomes missing")
    require("struct orchestra_telemetry_v8" in KERNEL_V8 and
            "policy_cache_hit_count" in KERNEL_V8 and
            "unsupported_action_count" in KERNEL_V8 and
            "prediction_fallback_count" in KERNEL_V8 and
            "state_generation_change_count" in KERNEL_V8 and
            "signal_generation_change_count" in KERNEL_V8,
            "v8 policy/action/fallback telemetry missing")
    require("orch_runtime_v8" in BPF and "orch_meta_v8" in BPF and
            "orch_entry_v8" in BPF and "orch_task_v8" in BPF and
            "orch_diag_v8" in BPF and "orch_tel_v8" in BPF,
            "kernel v8 maps must be part of the canonical BPF object")
    require("orchestra_read_runtime_state" in BPF and
            "orchestra_build_state" in BPF and
            "orchestra_policy_lookup" in BPF and
            "orchestra_controller_gate" in BPF and
            "orchestra_validate_action" in BPF and
            "orchestra_decide" in BPF and
            "orchestra_execute_action" in BPF and
            "orchestra_record_result" in BPF,
            "canonical kernel decision pipeline is incomplete")
    require(BPF.index("orchestra_read_runtime_state") <
            BPF.index("orchestra_build_state") <
            BPF.index("orchestra_policy_lookup") <
            BPF.index("orchestra_controller_gate") <
            BPF.index("orchestra_validate_action") <
            BPF.index("orchestra_execute_action"),
            "kernel decision stages must remain ordered in source")
    require("policy_default_v8" in BPF and
            "BRIDGE_FALLBACK_UNSUPPORTED_ACTION" in BPF and
            "ORCHESTRA_CTRL_ROLLBACK" in BPF and
            "ORCHESTRA_CTRL_RECOVERY" in BPF and
            "orchestra_record_defer_v8" in BPF and
            "cpu_is_online" in BPF,
            "safe controller/action fallback semantics missing")
    require("BRIDGE_RUNTIME_V8_MAP_NAME" in LOADER and
            "BRIDGE_POLICY_ENTRY_V8_MAP_NAME" in LOADER and
            "ORCHESTRA_KERNEL_POLICY_ENTRY_COUNT" in LOADER and
            "--policy-commit" in BRIDGE and
            "EVALUATE freezes the active policy" in BRIDGE,
            "loader/control plane must expose v8 policy maps and lifecycle")
    require("m.s3 = m.s3_conditioned" in ENGINE and
            "if (m.s4_burst < m.s4) m.s4 = m.s4_burst" in ENGINE,
            "corrected conditioned-S3/burst-S4 semantics must remain canonical")
    require("calibrated_prediction_confidence" in ENGINE and
            "calibrate_fixed_gain" in ENGINE and "kalman" not in ENGINE.lower(),
            "offline fixed-gain predictor must not regress to adaptive Kalman")
    print("PASS sched_ext source safety invariants")


if __name__ == "__main__":
    main()
