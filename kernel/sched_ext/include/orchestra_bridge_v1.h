/*
 * ORCHESTRA-OS Stage 7 — Userspace-to-BPF Signal Bridge v1
 *
 * All fields use fixed-width integer types.  All bridge structs are
 * packed to guarantee deterministic sizes across userspace and BPF.
 */
#ifndef ORCHESTRA_BRIDGE_V1_H
#define ORCHESTRA_BRIDGE_V1_H

#ifdef __BPF__
#include <vmlinux.h>
typedef __u32 uint32_t;
typedef __u64 uint64_t;
typedef __s32 int32_t;
#define UINT64_C(v) (v ## ULL)
#else
#include <stdint.h>
#endif

/* --- Canonical action enum --- */
enum orchestra_bridge_action {
    BRIDGE_ACT_RUN      = 0,
    BRIDGE_ACT_YIELD    = 1,
    BRIDGE_ACT_MIGRATE  = 2,
    BRIDGE_ACT_THROTTLE = 3,
    BRIDGE_ACT_SLEEP    = 4
};

/* --- Controller state enum --- */
enum orchestra_bridge_ctrl_state {
    BRIDGE_CTRL_NORMAL    = 0,
    BRIDGE_CTRL_DEGRADED = 1,
    BRIDGE_CTRL_SATURATED = 2,
    BRIDGE_CTRL_DISABLED = 3,
    BRIDGE_CTRL_ROLLBACK  = 4,
    BRIDGE_CTRL_RECOVERY  = 5
};

/* --- Policy mode enum --- */
enum orchestra_bridge_policy_mode {
    BRIDGE_POLICY_TRAIN    = 0,
    BRIDGE_POLICY_ADAPT    = 1,
    BRIDGE_POLICY_EVALUATE = 2
};

/* --- Capability flags --- */
#define BRIDGE_CAP_RUN           (1u << 0)
#define BRIDGE_CAP_YIELD         (1u << 1)
#define BRIDGE_CAP_MIGRATE       (1u << 2)
#define BRIDGE_CAP_THROTTLE      (1u << 3)
#define BRIDGE_CAP_SLEEP         (1u << 4)
#define BRIDGE_CAP_ADAPTIVE_SLICE (1u << 5)

/* --- Publication status --- */
#define BRIDGE_PUB_OK             0u
#define BRIDGE_PUB_NOT_LOADED     1u
#define BRIDGE_PUB_SCHEMA_MISMATCH 2u
#define BRIDGE_PUB_MAP_ERROR      3u
#define BRIDGE_PUB_READBACK_FAIL  4u
#define BRIDGE_PUB_GEN_OVERFLOW   5u
#define BRIDGE_PUB_POLICY_INVALID 6u

/* --- Task identity rejection reasons --- */
#define BRIDGE_ID_OK             0u
#define BRIDGE_ID_PID_MISMATCH   1u
#define BRIDGE_ID_TGID_MISMATCH  2u
#define BRIDGE_ID_COOKIE_MISMATCH 3u
#define BRIDGE_ID_EXPIRED        4u
#define BRIDGE_ID_EXITED         5u
#define BRIDGE_ID_STALE_GEN      6u

/* --- Sizing --- */
#define BRIDGE_SLOT_COUNT         2u
#define BRIDGE_MAX_TASKS          128u
#define BRIDGE_CPU_ANY            0xFFFFFFFFu

#define BRIDGE_SLICE_MIN_NS       UINT64_C(500000)
#define BRIDGE_SLICE_YIELD_NS     UINT64_C(1000000)
#define BRIDGE_SLICE_RUN_NS       UINT64_C(5000000)
#define BRIDGE_SLICE_MAX_NS       UINT64_C(100000000)
#define BRIDGE_THROTTLE_MAX_NS    UINT64_C(1000000000)
#define BRIDGE_SLEEP_MAX_NS       UINT64_C(5000000000)
#define BRIDGE_EXPIRY_MAX_NS      UINT64_C(60000000000)

/* ================================================================
 * Bridge control record (BPF ARRAY, 1 entry)
 * ================================================================ */
struct bridge_control {
    uint32_t magic;
    uint32_t format_version;
    uint32_t schema_version;
    uint32_t active_slot;
    uint64_t published_generation;
    uint64_t policy_generation;
    uint32_t controller_state;
    uint32_t policy_mode;
    uint32_t capability_flags;
    uint32_t publication_status;
    uint64_t last_update_ns;
    uint64_t policy_digest_hi;
    uint32_t policy_format_ver;
    uint32_t policy_schema_ver;
} __attribute__((packed));

/* ================================================================
 * Per-slot directive (BPF ARRAY, 2 entries)
 * ================================================================ */
struct bridge_directive {
    uint64_t generation;
    uint32_t target_tgid;
    uint32_t target_pid;
    uint64_t task_cookie;
    uint32_t action;
    uint32_t target_cpu;
    uint64_t slice_ns;
    uint64_t not_before_ns;
    uint64_t throttle_interval_ns;
    uint64_t expiry_ns;
    uint32_t reserved;
} __attribute__((packed));

/* ================================================================
 * Per-task runtime state (BPF HASH)
 * ================================================================ */
struct bridge_task_state {
    uint64_t task_cookie;
    uint32_t current_action;
    uint32_t current_target_cpu;
    uint64_t current_slice_ns;
    uint64_t throttle_until_ns;
    uint64_t last_enqueue_ns;
} __attribute__((packed));

/* ================================================================
 * Telemetry v2 — extends Stage 6 with Stage 7 fields
 * ================================================================ */
struct bridge_telemetry {
    /* Stage 6 preserved */
    uint64_t load_count;
    uint64_t unload_count;
    uint64_t task_enable_count;
    uint64_t task_disable_count;
    uint64_t enqueue_count;
    uint64_t dispatch_count;
    uint64_t run_count;
    uint64_t yield_count;
    uint64_t fallback_count;
    uint64_t invalid_action_count;
    uint64_t dispatch_mismatch_count;
    uint64_t scheduler_error_count;

    /* Stage 7 — bridge */
    uint64_t bridge_stable_reads;
    uint64_t bridge_stale_reads;
    uint64_t bridge_unstable_reads;
    uint64_t bridge_missing_directive;
    uint64_t bridge_expired_directive;
    uint64_t bridge_id_rejections;
    uint64_t bridge_ctrl_rejections;

    /* Stage 7 — per-action */
    uint64_t migrate_requested;
    uint64_t migrate_effective;
    uint64_t migrate_cpu_invalid;
    uint64_t migrate_cpu_offline;
    uint64_t migrate_affinity_reject;
    uint64_t migrate_fallback;

    uint64_t throttle_requested;
    uint64_t throttle_effective;
    uint64_t throttle_excessive;
    uint64_t throttle_fallback;

    uint64_t sleep_requested;
    uint64_t sleep_effective;
    uint64_t sleep_excessive_deferral;
    uint64_t sleep_unsupported;
    uint64_t sleep_fallback;

    uint64_t adaptive_slice_count;
    uint64_t slice_overflow;
} __attribute__((packed));

#endif /* ORCHESTRA_BRIDGE_V1_H */
