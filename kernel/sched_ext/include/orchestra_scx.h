/*
 * ORCHESTRA-OS Stage 6 sched_ext MVP — shared definitions.
 *
 * This header defines the BPF map layouts, action enums, telemetry
 * structures, and constants shared between the BPF program and the
 * userspace loader.  No floating point, no dynamic allocation, no
 * filesystem access is permitted inside BPF.
 */
#ifndef ORCHESTRA_SCX_H
#define ORCHESTRA_SCX_H

#include "orchestra_abi.h"

/*
 * When compiled for BPF target (-target bpf): vmlinux.h must be included
 * before this header (common.bpf.h does this).  Kernel types __u32/__u64
 * are available.
 *
 * When compiled for userspace: stdint.h provides standard types.
 */
#ifdef __BPF__
/* vmlinux.h already included by common.bpf.h — use kernel types */
typedef __u32 uint32_t;
typedef __u64 uint64_t;
typedef __s32 int32_t;
#else
#include <stdint.h>
#endif

/* --- Canonical actions (subset for Stage 6) --- */

/* Historical spellings remain source-compatible, but their values come from
 * the single canonical C/BPF action ABI and cover all five actions. */
#define ORCHESTRA_ACT_RUN       ORCHESTRA_ACTION_RUN
#define ORCHESTRA_ACT_SLEEP     ORCHESTRA_ACTION_SLEEP
#define ORCHESTRA_ACT_MIGRATE   ORCHESTRA_ACTION_MIGRATE
#define ORCHESTRA_ACT_THROTTLE  ORCHESTRA_ACTION_THROTTLE
#define ORCHESTRA_ACT_YIELD     ORCHESTRA_ACTION_YIELD
#define ORCHESTRA_ACT_UNKNOWN   0xffu
typedef enum orchestra_action_id orchestra_action;

/* The frozen policy maps a compact state index to a canonical action.
 * Stage 6 uses a small, hardcoded 30-state lookup table. */
#define ORCHESTRA_POLICY_STATE_COUNT 30
#define ORCHESTRA_POLICY_TABLE_SIZE  ORCHESTRA_POLICY_STATE_COUNT

/* Slice bounds (nanoseconds) */
#define ORCHESTRA_SLICE_NS_DEFAULT   (5000000ULL)   /*  5 ms */
#define ORCHESTRA_SLICE_NS_YIELD     (1000000ULL)   /*  1 ms */
#define ORCHESTRA_SLICE_NS_MIN       ( 500000ULL)   /* 0.5 ms floor */

/* Maximum dispatch attempts before requeue fallback */
#define ORCHESTRA_MAX_DISPATCH_LOOPS 4

/* BPF map identifiers — must match orchestra_scx.c */
#define ORCHESTRA_MAP_POLICY         0
#define ORCHESTRA_MAP_TELEMETRY      1
#define ORCHESTRA_MAP_TASK_STATE     2

/* --- Policy entry (read-only from BPF) --- */
struct orchestra_policy_entry {
    uint32_t state;
    uint32_t action;   /* orchestra_action */
};

/* --- Per-task state (writable from BPF) --- */
struct orchestra_task_state {
    uint64_t optin_ts;
    uint32_t last_action;
    uint32_t fallback_count;
};

/* --- Aggregated telemetry (writable from BPF) --- */
struct orchestra_telemetry {
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
};

/* --- Opt-in policy: only explicitly selected tasks --- */
static inline int orchestra_should_optin(void)
{
    /* Stage 6: all SCHED_EXT tasks are eligible.
     * Future stages add PID filtering. */
    return 1;
}

/* --- Minimal frozen policy for Stage 6 --- */
static inline orchestra_action orchestra_frozen_policy(uint32_t state)
{
    if (state >= ORCHESTRA_POLICY_STATE_COUNT)
        return ORCHESTRA_ACT_RUN;

    /* Simplified lookup: low-CPU states → RUN, high-CPU states → YIELD */
    if (state < 15)
        return ORCHESTRA_ACT_RUN;
    return ORCHESTRA_ACT_YIELD;
}

#endif /* ORCHESTRA_SCX_H */
