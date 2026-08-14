/* SPDX-License-Identifier: GPL-2.0 */
/*
 * ORCHESTRA-OS sched_ext prototype, bridge ABI v2.
 *
 * Target API: Linux 7.0 sched_ext (dsq_insert / dsq_move). Wrappers below were
 * reviewed against v6.13+ kfunc rename: insert replaces dispatch, move
 * replaces dispatch_from_dsq. A compile-only token rename is still not a port.
 *
 * Safety model:
 *   - full switch avoids fair-class-over-ext starvation from partial mode;
 *   - every absent, unstable, stale or invalid directive dispatches as RUN;
 *   - directives are coherent BPF_F_LOCK snapshots keyed by exact task
 *     lifetime identity (TGID, TID, start_boottime);
 *   - SLEEP and exhausted THROTTLE budgets enter a deadline-ordered DSQ which
 *     is drained by a bounded timer callback;
 *   - YIELD enters the shared global queue tail;
 *   - MIGRATE is accepted only for a currently online, affinity-allowed CPU;
 *   - task/outcome records carry identity, generation, action and CPUs.
 */
#include <scx/common.bpf.h>
#include "include/orchestra_bridge_v1.h"

/*
 * tools/sched_ext/include/scx/enums.autogen.bpf.h replaces DSQ/kick/enq
 * constants with zeroed volatile ksyms filled only by SCX_OPS_LOAD(). This
 * loader uses generic libbpf, so restore the running kernel's vmlinux enum
 * values or enqueue hits DSQ 0x0 and the scheduler aborts.
 */
#undef SCX_DSQ_GLOBAL
#undef SCX_DSQ_LOCAL
#undef SCX_DSQ_LOCAL_ON
#undef SCX_DSQ_FLAG_BUILTIN
#undef SCX_KICK_IDLE
#undef SCX_ENQ_HEAD

char _license[] SEC("license") = "GPL";

#if ORCHESTRA_SCX_API_VERSION != 70012u
#error "Review DSQ insertion/struct_ops semantics before changing the sched_ext API target"
#endif

#define ORCHESTRA_U64_MAX (~(uint64_t)0)
#define orchestra_dsq_insert(p, dsq, slice, flags) \
    scx_bpf_dsq_insert((p), (dsq), (slice), (flags))
#define orchestra_dsq_insert_vtime(p, dsq, slice, vtime, flags) \
    scx_bpf_dsq_insert_vtime((p), (dsq), (slice), (vtime), (flags))
#define orchestra_dsq_move_from_dsq(it, p, dsq, flags) \
    scx_bpf_dsq_move((it), (p), (dsq), (flags))

struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, 1);
    __type(key, uint32_t);
    __type(value, struct bridge_control);
} orch_control SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, BRIDGE_MAX_TASKS);
    __type(key, struct orchestra_task_identity);
    __type(value, struct bridge_directive);
} orch_directives SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, BRIDGE_MAX_TASKS);
    __type(key, struct orchestra_pid_key);
    __type(value, struct bridge_identity_record);
} orch_identity SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, BRIDGE_MAX_TASKS);
    __type(key, struct orchestra_task_identity);
    __type(value, struct bridge_task_state);
} orch_task_state SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, BRIDGE_MAX_TASKS);
    __type(key, struct orchestra_task_identity);
    __type(value, struct bridge_task_telemetry);
} orch_task_tel SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, 1);
    __type(key, uint32_t);
    __type(value, struct bridge_telemetry);
} orch_telemetry SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, 1);
    __type(key, uint32_t);
    __type(value, struct bridge_defer_timer);
} orch_defer_tmr SEC(".maps");

struct directive_snapshot {
    uint64_t scheduler_epoch;
    uint64_t generation;
    uint64_t slice_ns;
    uint64_t not_before_ns;
    uint64_t throttle_period_ns;
    uint64_t throttle_budget_ns;
    uint64_t expiry_ns;
    uint32_t action;
    uint32_t target_cpu;
    uint32_t controller_state;
    uint32_t policy_mode;
    uint64_t policy_generation;
};

struct control_snapshot {
    uint64_t scheduler_epoch;
    uint64_t last_generation;
    uint64_t heartbeat_ns;
    uint64_t lease_ns;
    uint64_t policy_generation;
    uint32_t controller_state;
    uint32_t policy_mode;
    uint32_t valid;
};

static __always_inline struct bridge_telemetry *global_tel(void)
{
    uint32_t key = 0;

    return bpf_map_lookup_elem(&orch_telemetry, &key);
}

static __always_inline void tel_inc(uint64_t *counter)
{
    if (counter)
        __sync_fetch_and_add(counter, 1);
}

static __always_inline struct orchestra_task_identity task_identity(
    const struct task_struct *p)
{
    struct orchestra_task_identity id = {
        .tgid = p->tgid,
        .tid = p->pid,
        .start_boottime_ns = p->start_boottime,
    };

    return id;
}

static __always_inline int identity_equal(
    const struct orchestra_task_identity *a,
    const struct orchestra_task_identity *b)
{
    return a->tgid == b->tgid && a->tid == b->tid &&
           a->start_boottime_ns == b->start_boottime_ns;
}

static __always_inline int snapshot_control(struct control_snapshot *out)
{
    struct bridge_control *ctl;
    uint32_t key = 0;

    ctl = bpf_map_lookup_elem(&orch_control, &key);
    if (!ctl)
        return 0;

    bpf_spin_lock(&ctl->lock);
    if (ctl->magic == ORCHESTRA_ABI_MAGIC &&
        ctl->abi_version == ORCHESTRA_ABI_VERSION &&
        ctl->value_size == sizeof(*ctl) &&
        ctl->scx_api_version == ORCHESTRA_SCX_API_VERSION &&
        (ctl->capability_flags & BRIDGE_REQUIRED_CAPS) == BRIDGE_REQUIRED_CAPS &&
        ctl->scheduler_epoch != 0) {
        out->scheduler_epoch = ctl->scheduler_epoch;
        out->last_generation = ctl->last_generation;
        out->heartbeat_ns = ctl->publisher_heartbeat_ns;
        out->lease_ns = ctl->publisher_lease_ns;
        out->policy_generation = ctl->policy_generation;
        out->controller_state = ctl->controller_state;
        out->policy_mode = ctl->policy_mode;
        out->valid = 1;
    }
    bpf_spin_unlock(&ctl->lock);
    return out->valid;
}

static __always_inline int control_snapshot_equal(
    const struct control_snapshot *a, const struct control_snapshot *b)
{
    return a->valid && b->valid &&
           a->scheduler_epoch == b->scheduler_epoch &&
           a->last_generation == b->last_generation &&
           a->heartbeat_ns == b->heartbeat_ns &&
           a->lease_ns == b->lease_ns &&
           a->policy_generation == b->policy_generation &&
           a->controller_state == b->controller_state &&
           a->policy_mode == b->policy_mode;
}

static __always_inline int action_allowed(uint32_t action, uint32_t state)
{
    switch (state) {
    case ORCHESTRA_CTRL_NORMAL:
        return 1;
    case ORCHESTRA_CTRL_DEGRADED:
        return action == ORCHESTRA_ACTION_RUN ||
               action == ORCHESTRA_ACTION_YIELD ||
               action == ORCHESTRA_ACTION_THROTTLE;
    case ORCHESTRA_CTRL_RECOVERY:
        return action == ORCHESTRA_ACTION_RUN ||
               action == ORCHESTRA_ACTION_YIELD;
    default:
        return action == ORCHESTRA_ACTION_RUN;
    }
}

static __always_inline int load_directive(
    struct task_struct *p, struct directive_snapshot *out,
    uint32_t *fallback_reason)
{
    struct bridge_telemetry *tel = global_tel();
    struct orchestra_task_identity id = task_identity(p);
    struct orchestra_task_identity value_id = {};
    struct control_snapshot ctl = {};
    struct control_snapshot verify_ctl = {};
    struct bridge_directive *dir;
    uint64_t now = bpf_ktime_get_ns();
    uint32_t abi_version = 0, value_size = 0;
    int coherent = 0;

    dir = bpf_map_lookup_elem(&orch_directives, &id);
    if (!dir) {
        *fallback_reason = BRIDGE_FALLBACK_NO_DIRECTIVE;
        return 0;
    }

    /* The control record and per-task value form one logical snapshot.  A
     * writer may update them between locks, so validate a control/directive/
     * control sequence and retry once.  Unstable publication safely falls
     * back to RUN; no shared cross-CPU cache is mutated. */
#pragma unroll
    for (int attempt = 0; attempt < 2; attempt++) {
        __builtin_memset(&ctl, 0, sizeof(ctl));
        __builtin_memset(&verify_ctl, 0, sizeof(verify_ctl));
        if (!snapshot_control(&ctl))
            continue;

        bpf_spin_lock(&dir->lock);
        abi_version = dir->abi_version;
        value_size = dir->value_size;
        out->scheduler_epoch = dir->scheduler_epoch;
        out->generation = dir->generation;
        value_id = dir->identity;
        out->action = dir->action;
        out->target_cpu = dir->target_cpu;
        out->slice_ns = dir->slice_ns;
        out->not_before_ns = dir->not_before_ns;
        out->throttle_period_ns = dir->throttle_period_ns;
        out->throttle_budget_ns = dir->throttle_budget_ns;
        out->expiry_ns = dir->expiry_ns;
        out->controller_state = dir->controller_state;
        out->policy_mode = dir->policy_mode;
        out->policy_generation = dir->policy_generation;
        bpf_spin_unlock(&dir->lock);

        if (snapshot_control(&verify_ctl) &&
            control_snapshot_equal(&ctl, &verify_ctl) &&
            out->generation != 0 &&
            out->generation <= ctl.last_generation) {
            coherent = 1;
            break;
        }
    }
    if (!coherent) {
        *fallback_reason = BRIDGE_FALLBACK_UNSTABLE_PUBLICATION;
        return 0;
    }

    if (ctl.lease_ns == 0 || ctl.lease_ns > BRIDGE_LEASE_MAX_NS ||
        ctl.heartbeat_ns == 0 || ctl.heartbeat_ns > now ||
        now - ctl.heartbeat_ns > ctl.lease_ns) {
        *fallback_reason = BRIDGE_FALLBACK_STALE_LEASE;
        if (tel)
            tel_inc(&tel->stale_lease_count);
        return 0;
    }

    if (abi_version != ORCHESTRA_ABI_VERSION || value_size != sizeof(*dir) ||
        out->scheduler_epoch != ctl.scheduler_epoch) {
        *fallback_reason = BRIDGE_FALLBACK_BAD_ABI;
        return 0;
    }
    if (!identity_equal(&id, &value_id) || id.start_boottime_ns == 0) {
        *fallback_reason = BRIDGE_FALLBACK_BAD_IDENTITY;
        if (tel)
            tel_inc(&tel->invalid_identity_count);
        return 0;
    }
    if (out->expiry_ns == 0 || out->expiry_ns < now ||
        out->expiry_ns - now > BRIDGE_EXPIRY_MAX_NS) {
        *fallback_reason = BRIDGE_FALLBACK_EXPIRED;
        if (tel)
            tel_inc(&tel->expired_directive_count);
        return 0;
    }
    if (out->action >= ORCHESTRA_ACTION_COUNT) {
        *fallback_reason = BRIDGE_FALLBACK_BAD_ACTION;
        if (tel)
            tel_inc(&tel->invalid_action_count);
        return 0;
    }
    if (!action_allowed(out->action, ctl.controller_state) ||
        out->controller_state != ctl.controller_state ||
        out->policy_mode != ctl.policy_mode ||
        out->policy_generation != ctl.policy_generation) {
        *fallback_reason = BRIDGE_FALLBACK_CONTROLLER;
        return 0;
    }

    if (tel)
        tel_inc(&tel->accepted_directive_count);
    return 1;
}

static __always_inline uint64_t clamp_slice(uint64_t requested)
{
    if (requested == 0)
        return BRIDGE_SLICE_RUN_NS;
    if (requested < BRIDGE_SLICE_MIN_NS)
        return BRIDGE_SLICE_MIN_NS;
    if (requested > BRIDGE_SLICE_MAX_NS)
        return BRIDGE_SLICE_MAX_NS;
    return requested;
}

static __always_inline int cpu_allowed_online(struct task_struct *p,
                                               uint32_t cpu)
{
    const struct cpumask *online;
    int valid = 0;

    if (cpu == ORCHESTRA_CPU_ANY || cpu >= (uint32_t)scx_bpf_nr_cpu_ids())
        return 0;
    if (!bpf_cpumask_test_cpu(cpu, p->cpus_ptr))
        return 0;

    online = scx_bpf_get_online_cpumask();
    if (online) {
        valid = bpf_cpumask_test_cpu(cpu, online);
        scx_bpf_put_cpumask(online);
    }
    return valid;
}

static __always_inline struct bridge_task_state *get_task_state(
    const struct orchestra_task_identity *id, int create)
{
    struct bridge_task_state zero = {};
    struct bridge_task_state *state;

    state = bpf_map_lookup_elem(&orch_task_state, id);
    if (!state && create) {
        if (bpf_map_update_elem(&orch_task_state, id, &zero,
                                BPF_NOEXIST) != 0) {
            struct bridge_telemetry *tel = global_tel();
            if (tel)
                tel_inc(&tel->map_error_count);
            return NULL;
        }
        state = bpf_map_lookup_elem(&orch_task_state, id);
    }
    return state;
}

static __always_inline struct bridge_task_telemetry *get_task_tel(
    const struct orchestra_task_identity *id, int create)
{
    struct bridge_task_telemetry zero = {
        .dispatched_cpu = -1,
        .actual_cpu = -1,
    };
    struct bridge_task_telemetry *task_tel;

    task_tel = bpf_map_lookup_elem(&orch_task_tel, id);
    if (!task_tel && create) {
        if (bpf_map_update_elem(&orch_task_tel, id, &zero,
                                BPF_NOEXIST) != 0)
            return NULL;
        task_tel = bpf_map_lookup_elem(&orch_task_tel, id);
    }
    return task_tel;
}

static __always_inline void record_fallback(
    const struct orchestra_task_identity *id, uint32_t reason,
    int directive_was_present)
{
    struct bridge_telemetry *tel = global_tel();
    struct bridge_task_telemetry *task_tel;

    if (tel)
        tel_inc(&tel->fallback_count);
    /* Avoid filling telemetry with every untargeted full-switch task. */
    if (!directive_was_present)
        return;
    task_tel = get_task_tel(id, 1);
    if (task_tel) {
        bpf_spin_lock(&task_tel->lock);
        task_tel->fallback_count++;
        task_tel->fallback_reason = reason;
        bpf_spin_unlock(&task_tel->lock);
    }
}

static __always_inline void record_accepted(
    const struct orchestra_task_identity *id,
    const struct directive_snapshot *dir)
{
    struct bridge_task_telemetry *task_tel = get_task_tel(id, 1);
    uint64_t now = bpf_ktime_get_ns();

    if (!task_tel)
        return;
    bpf_spin_lock(&task_tel->lock);
    task_tel->generation = dir->generation;
    task_tel->action = dir->action;
    task_tel->requested_cpu = dir->target_cpu;
    task_tel->accepted_ns = now;
    task_tel->accepted_count++;
    task_tel->fallback_reason = BRIDGE_FALLBACK_NONE;
    bpf_spin_unlock(&task_tel->lock);
}

static __always_inline void record_dispatched(
    const struct orchestra_task_identity *id, uint64_t generation,
    uint32_t action, int32_t cpu)
{
    struct bridge_telemetry *tel = global_tel();
    struct bridge_task_telemetry *task_tel = get_task_tel(id, 1);
    uint64_t now = bpf_ktime_get_ns();

    if (tel)
        tel_inc(&tel->dispatched_action_count);
    if (!task_tel)
        return;
    bpf_spin_lock(&task_tel->lock);
    task_tel->generation = generation;
    task_tel->action = action;
    task_tel->dispatched_cpu = cpu;
    task_tel->dispatched_ns = now;
    task_tel->dispatched_count++;
    bpf_spin_unlock(&task_tel->lock);
}

static __always_inline void dispatch_run(struct task_struct *p,
                                         uint64_t enq_flags,
                                         int direct_local, int32_t cpu)
{
    struct bridge_telemetry *tel = global_tel();

    orchestra_dsq_insert(p, direct_local ? SCX_DSQ_LOCAL : SCX_DSQ_GLOBAL,
                         BRIDGE_SLICE_RUN_NS, enq_flags);
    if (tel)
        tel_inc(&tel->run_dispatched_count);
    (void)cpu;
}

static __always_inline int defer_task(
    struct task_struct *p, const struct orchestra_task_identity *id,
    struct bridge_task_state *state, uint64_t eligible_ns,
    uint64_t generation, uint32_t action, uint64_t enq_flags)
{
    struct bridge_telemetry *tel = global_tel();

    if (!state || eligible_ns <= bpf_ktime_get_ns())
        return 0;
    bpf_spin_lock(&state->lock);
    state->generation = generation;
    state->action = action;
    state->eligible_ns = eligible_ns;
    state->flags |= BRIDGE_TASK_F_DEFERRED;
    bpf_spin_unlock(&state->lock);
    orchestra_dsq_insert_vtime(p, BRIDGE_DEFERRED_DSQ,
                               BRIDGE_SLICE_RUN_NS, eligible_ns, enq_flags);
    if (tel)
        tel_inc(&tel->deferred_count);
    /* Insertion into the deferred DSQ is queued/deferred, not CPU dispatch. */
    return 1;
}

static __always_inline void place_with_snapshot(
    struct task_struct *p, uint64_t enq_flags,
    const struct directive_snapshot *dir, int have_directive,
    uint32_t fallback_reason, int direct_insert, int direct_local,
    int32_t selected_cpu)
{
    struct orchestra_task_identity id = task_identity(p);
    struct bridge_telemetry *tel = global_tel();
    struct bridge_task_state *state;
    uint64_t now = bpf_ktime_get_ns();
    uint64_t slice;

    if (tel)
        tel_inc(&tel->placement_count);
    if (tel && direct_insert)
        tel_inc(&tel->select_cpu_direct_insert_count);
    if (!have_directive) {
        record_fallback(&id, fallback_reason,
                        fallback_reason != BRIDGE_FALLBACK_NO_DIRECTIVE);
        dispatch_run(p, enq_flags, direct_local, selected_cpu);
        return;
    }

    record_accepted(&id, dir);
    state = get_task_state(&id, 1);
    if (!state) {
        record_fallback(&id, BRIDGE_FALLBACK_MAP_ERROR, 1);
        dispatch_run(p, enq_flags, direct_local, selected_cpu);
        return;
    }
    bpf_spin_lock(&state->lock);
    if (state->generation != dir->generation || state->action != dir->action) {
        state->generation = dir->generation;
        state->period_start_ns = now;
        state->runtime_used_ns = 0;
        state->running_since_ns = 0;
        state->eligible_ns = 0;
        state->action = dir->action;
        state->requested_cpu = dir->target_cpu;
        state->dispatched_cpu = ORCHESTRA_CPU_ANY;
        state->flags = 0;
    }
    state->last_enqueue_ns = now;
    bpf_spin_unlock(&state->lock);
    slice = clamp_slice(dir->slice_ns);

    switch (dir->action) {
    case ORCHESTRA_ACTION_RUN:
        orchestra_dsq_insert(p, direct_local ? SCX_DSQ_LOCAL : SCX_DSQ_GLOBAL,
                             slice, enq_flags);
        if (tel)
            tel_inc(&tel->run_dispatched_count);
        bpf_spin_lock(&state->lock);
        state->dispatched_cpu = direct_local ? (uint32_t)selected_cpu : ORCHESTRA_CPU_ANY;
        bpf_spin_unlock(&state->lock);
        record_dispatched(&id, dir->generation, dir->action,
                          direct_local ? selected_cpu : -1);
        return;

    case ORCHESTRA_ACTION_YIELD:
        /* Queue-tail relinquish with the minimum legal opportunity.  A lone
         * task remains work-conserving, while peers get priority over it. */
        orchestra_dsq_insert(p, SCX_DSQ_GLOBAL, BRIDGE_SLICE_MIN_NS,
                             enq_flags & ~SCX_ENQ_HEAD);
        if (tel)
            tel_inc(&tel->yield_dispatched_count);
        bpf_spin_lock(&state->lock);
        state->dispatched_cpu = ORCHESTRA_CPU_ANY;
        bpf_spin_unlock(&state->lock);
        record_dispatched(&id, dir->generation, dir->action, -1);
        return;

    case ORCHESTRA_ACTION_SLEEP:
        if (dir->not_before_ns <= now ||
            dir->not_before_ns - now > BRIDGE_SLEEP_MAX_NS) {
            record_fallback(&id, BRIDGE_FALLBACK_BAD_PARAMETERS, 1);
            dispatch_run(p, enq_flags, direct_local, selected_cpu);
            return;
        }
        if (tel) {
            tel_inc(&tel->sleep_accepted_count);
            tel_inc(&tel->sleep_deferred_count);
        }
        if (!defer_task(p, &id, state, dir->not_before_ns,
                        dir->generation, dir->action, enq_flags)) {
            record_fallback(&id, BRIDGE_FALLBACK_MAP_ERROR, 1);
            dispatch_run(p, enq_flags, direct_local, selected_cpu);
        }
        return;

    case ORCHESTRA_ACTION_THROTTLE: {
        uint64_t period = dir->throttle_period_ns;
        uint64_t budget = dir->throttle_budget_ns;
        uint64_t elapsed;
        uint64_t remaining;

        if (period < BRIDGE_SLICE_MIN_NS || period > BRIDGE_THROTTLE_MAX_NS ||
            budget < BRIDGE_SLICE_MIN_NS || budget >= period) {
            record_fallback(&id, BRIDGE_FALLBACK_BAD_PARAMETERS, 1);
            dispatch_run(p, enq_flags, direct_local, selected_cpu);
            return;
        }
        if (tel)
            tel_inc(&tel->throttle_accepted_count);
        bpf_spin_lock(&state->lock);
        elapsed = now - state->period_start_ns;
        if (elapsed >= period) {
            state->period_start_ns = now;
            state->runtime_used_ns = 0;
        }
        remaining = state->runtime_used_ns;
        bpf_spin_unlock(&state->lock);
        if (remaining >= budget) {
            bpf_spin_lock(&state->lock);
            state->flags |= BRIDGE_TASK_F_THROTTLED;
            bpf_spin_unlock(&state->lock);
            if (tel)
                tel_inc(&tel->throttle_deferred_count);
            bpf_spin_lock(&state->lock);
            elapsed = state->period_start_ns + period;
            bpf_spin_unlock(&state->lock);
            if (!defer_task(p, &id, state,
                            elapsed,
                            dir->generation, dir->action, enq_flags)) {
                record_fallback(&id, BRIDGE_FALLBACK_MAP_ERROR, 1);
                dispatch_run(p, enq_flags, direct_local, selected_cpu);
            }
            return;
        }
        remaining = budget - remaining;
        if (slice > remaining)
            slice = remaining;
        orchestra_dsq_insert(p, direct_local ? SCX_DSQ_LOCAL : SCX_DSQ_GLOBAL,
                             slice, enq_flags);
        bpf_spin_lock(&state->lock);
        state->dispatched_cpu = direct_local ? (uint32_t)selected_cpu : ORCHESTRA_CPU_ANY;
        bpf_spin_unlock(&state->lock);
        record_dispatched(&id, dir->generation, dir->action,
                          direct_local ? selected_cpu : -1);
        return;
    }

    case ORCHESTRA_ACTION_MIGRATE:
        if (!cpu_allowed_online(p, dir->target_cpu)) {
            if (tel)
                tel_inc(&tel->invalid_cpu_count);
            record_fallback(&id, BRIDGE_FALLBACK_BAD_CPU, 1);
            /* A target which became illegal between selection and insertion
             * must not receive a LOCAL direct dispatch. */
            dispatch_run(p, enq_flags, 0, -1);
            return;
        }
        if (tel)
            tel_inc(&tel->migrate_accepted_count);
        /* select_cpu pairs SCX_DSQ_LOCAL with its returned target.  Normal
         * re-enqueues have no returned CPU, so use the explicit LOCAL_ON DSQ
         * after repeating the online/affinity check above. */
        if (!direct_local || selected_cpu != (int32_t)dir->target_cpu) {
            orchestra_dsq_insert(p, SCX_DSQ_LOCAL_ON | dir->target_cpu,
                                 slice, enq_flags);
            bpf_spin_lock(&state->lock);
            state->dispatched_cpu = dir->target_cpu;
            bpf_spin_unlock(&state->lock);
            if (tel)
                tel_inc(&tel->migrate_dispatched_count);
            record_dispatched(&id, dir->generation, dir->action,
                              (int32_t)dir->target_cpu);
            return;
        }
        orchestra_dsq_insert(p, SCX_DSQ_LOCAL, slice, enq_flags);
        bpf_spin_lock(&state->lock);
        state->dispatched_cpu = dir->target_cpu;
        bpf_spin_unlock(&state->lock);
        if (tel)
            tel_inc(&tel->migrate_dispatched_count);
        record_dispatched(&id, dir->generation, dir->action, selected_cpu);
        return;

    default:
        if (tel)
            tel_inc(&tel->invalid_action_count);
        record_fallback(&id, BRIDGE_FALLBACK_BAD_ACTION, 1);
        dispatch_run(p, enq_flags, direct_local, selected_cpu);
        return;
    }
}

static int deferred_timerfn(void *map, int *key, struct bpf_timer *timer)
{
    struct task_struct *p;
    struct bridge_telemetry *global = global_tel();
    uint64_t now = bpf_ktime_get_ns();
    uint32_t scanned = 0;

    if (global)
        tel_inc(&global->deferred_timer_tick_count);
    bpf_rcu_read_lock();
    bpf_for_each(scx_dsq, p, BRIDGE_DEFERRED_DSQ, 0) {
        struct orchestra_task_identity id;
        struct bridge_task_state *state;
        struct bridge_task_telemetry *task_tel;
        uint64_t generation;
        uint64_t old_runtime = 0;
        uint32_t action;
        uint32_t old_action = ORCHESTRA_ACTION_RUN;
        uint32_t old_cpu = ORCHESTRA_CPU_ANY;
        uint32_t old_flags = 0;
        int32_t cpu;

        if (scanned++ >= BRIDGE_DEFER_SCAN_MAX)
            break;
        if (global)
            tel_inc(&global->deferred_timer_scanned_count);
        /* The DSQ is ordered by eligible_ns, so later entries are future too. */
        if (p->scx.dsq_vtime > now) {
            if (global)
                tel_inc(&global->deferred_timer_future_count);
            break;
        }
        id = task_identity(p);
        state = get_task_state(&id, 0);
        /* Invalid/missing state must release safely as RUN. Leaving an
         * unrecognized task in the deferred DSQ would violate progress. */
        cpu = scx_bpf_pick_any_cpu(p->cpus_ptr, 0);
        if (cpu < 0 || !cpu_allowed_online(p, (uint32_t)cpu)) {
            if (global)
                tel_inc(&global->deferred_cpu_failure_count);
            continue;
        }
        generation = 0;
        action = ORCHESTRA_ACTION_RUN;
        task_tel = get_task_tel(&id, 0);
        /* Publish runnable state before moving the task. Another CPU may run
         * it immediately after dispatch_from_dsq succeeds. */
        if (state) {
            bpf_spin_lock(&state->lock);
            generation = state->generation;
            action = state->action;
            old_flags = state->flags;
            old_cpu = state->dispatched_cpu;
            old_action = state->action;
            old_runtime = state->runtime_used_ns;
            state->flags &= ~(BRIDGE_TASK_F_DEFERRED |
                              BRIDGE_TASK_F_THROTTLED);
            state->dispatched_cpu = (uint32_t)cpu;
            if (state->eligible_ns > now) {
                state->action = ORCHESTRA_ACTION_RUN;
                state->runtime_used_ns = 0;
                action = ORCHESTRA_ACTION_RUN;
            }
            bpf_spin_unlock(&state->lock);
        }
        if (orchestra_dsq_move_from_dsq(
                BPF_FOR_EACH_ITER, p, SCX_DSQ_LOCAL_ON | cpu, 0)) {
            if (global) {
                tel_inc(&global->deferred_release_count);
                tel_inc(&global->dispatched_action_count);
            }
            if (task_tel) {
                bpf_spin_lock(&task_tel->lock);
                task_tel->generation = generation;
                task_tel->action = action;
                task_tel->dispatched_cpu = cpu;
                task_tel->dispatched_ns = now;
                task_tel->dispatched_count++;
                /* Eligibility/budget enforcement becomes effective when the
                 * deferred task is released, not when it was merely queued. */
                if (action == ORCHESTRA_ACTION_SLEEP ||
                    action == ORCHESTRA_ACTION_THROTTLE)
                    task_tel->effective_count++;
                bpf_spin_unlock(&task_tel->lock);
            }
            scx_bpf_kick_cpu(cpu, SCX_KICK_IDLE);
        } else if (state) {
            if (global)
                tel_inc(&global->deferred_release_failure_count);
            /* The task remains in the deferred DSQ; restore its queue state. */
            bpf_spin_lock(&state->lock);
            state->flags = old_flags;
            state->dispatched_cpu = old_cpu;
            state->action = old_action;
            state->runtime_used_ns = old_runtime;
            bpf_spin_unlock(&state->lock);
        }
    }
    bpf_rcu_read_unlock();
    if (bpf_timer_start(timer, BRIDGE_DEFER_TICK_NS, 0) != 0)
        scx_bpf_error("ORCHESTRA deferred timer re-arm failed");
    return 0;
}

s32 BPF_STRUCT_OPS_SLEEPABLE(orchestra_sched_init)
{
    struct bridge_control *ctl;
    struct bridge_defer_timer *defer;
    struct bridge_telemetry *tel = global_tel();
    uint32_t key = 0;
    uint64_t epoch = bpf_ktime_get_ns();
    int ret;

    if (tel)
        tel_inc(&tel->load_count);
    if (!epoch)
        epoch = 1;

    ctl = bpf_map_lookup_elem(&orch_control, &key);
    if (!ctl)
        return -ESRCH;
    bpf_spin_lock(&ctl->lock);
    ctl->magic = ORCHESTRA_ABI_MAGIC;
    ctl->abi_version = ORCHESTRA_ABI_VERSION;
    ctl->value_size = sizeof(*ctl);
    ctl->capability_flags = BRIDGE_REQUIRED_CAPS;
    ctl->scheduler_epoch = epoch;
    ctl->last_generation = 0;
    ctl->publisher_heartbeat_ns = 0;
    ctl->publisher_lease_ns = 0;
    ctl->policy_generation = 0;
    ctl->controller_state = ORCHESTRA_CTRL_NORMAL;
    ctl->policy_mode = ORCHESTRA_POLICY_EVALUATE;
    ctl->publication_status = BRIDGE_PUB_OK;
    ctl->scx_api_version = ORCHESTRA_SCX_API_VERSION;
    bpf_spin_unlock(&ctl->lock);

    ret = scx_bpf_create_dsq(BRIDGE_DEFERRED_DSQ, -1);
    if (ret)
        return ret;
    defer = bpf_map_lookup_elem(&orch_defer_tmr, &key);
    if (!defer)
        return -ESRCH;
    ret = bpf_timer_init(&defer->timer, &orch_defer_tmr, CLOCK_MONOTONIC);
    if (ret)
        return ret;
    ret = bpf_timer_set_callback(&defer->timer, deferred_timerfn);
    if (ret)
        return ret;
    return bpf_timer_start(&defer->timer, BRIDGE_DEFER_TICK_NS, 0);
}

void BPF_STRUCT_OPS(orchestra_sched_exit, struct scx_exit_info *ei)
{
    struct bridge_telemetry *tel = global_tel();

    if (!tel)
        return;
    tel_inc(&tel->unload_count);
    if (ei && (ei->kind == SCX_EXIT_ERROR || ei->kind == SCX_EXIT_UNREG))
        tel_inc(&tel->scheduler_error_count);
}

s32 BPF_STRUCT_OPS(orchestra_sched_enable, struct task_struct *p)
{
    struct orchestra_pid_key key = { .tgid = p->tgid, .tid = p->pid };
    struct bridge_identity_record identity = {
        .start_boottime_ns = p->start_boottime,
    };
    struct bridge_control *ctl;
    struct bridge_telemetry *tel = global_tel();
    uint32_t zero = 0;

    ctl = bpf_map_lookup_elem(&orch_control, &zero);
    if (ctl)
        identity.scheduler_epoch = ctl->scheduler_epoch;
    if (bpf_map_update_elem(&orch_identity, &key, &identity, BPF_ANY) != 0 && tel)
        tel_inc(&tel->map_error_count);
    if (tel)
        tel_inc(&tel->task_enable_count);
    return 0;
}

void BPF_STRUCT_OPS(orchestra_sched_disable, struct task_struct *p)
{
    struct orchestra_task_identity id = task_identity(p);
    struct orchestra_pid_key key = { .tgid = p->tgid, .tid = p->pid };
    struct bridge_identity_record *record;
    struct bridge_telemetry *tel = global_tel();

    record = bpf_map_lookup_elem(&orch_identity, &key);
    if (record && record->start_boottime_ns == id.start_boottime_ns)
        bpf_map_delete_elem(&orch_identity, &key);
    bpf_map_delete_elem(&orch_directives, &id);
    bpf_map_delete_elem(&orch_task_state, &id);
    bpf_map_delete_elem(&orch_task_tel, &id);
    if (tel)
        tel_inc(&tel->task_disable_count);
}

s32 BPF_STRUCT_OPS(orchestra_sched_select_cpu, struct task_struct *p,
                   s32 prev_cpu, u64 wake_flags)
{
    struct directive_snapshot dir = {};
    uint32_t fallback = BRIDGE_FALLBACK_NO_DIRECTIVE;
    int have_directive = load_directive(p, &dir, &fallback);
    struct bridge_telemetry *tel = global_tel();
    bool is_idle = false;
    s32 cpu;

    if (tel)
        tel_inc(&tel->select_cpu_count);
    if (have_directive && dir.action == ORCHESTRA_ACTION_MIGRATE &&
        cpu_allowed_online(p, dir.target_cpu)) {
        cpu = (s32)dir.target_cpu;
        is_idle = scx_bpf_test_and_clear_cpu_idle(cpu);
        /* LOCAL direct dispatch is paired with the CPU returned below. */
        place_with_snapshot(p, 0, &dir, 1, BRIDGE_FALLBACK_NONE, 1, 1, cpu);
        return cpu;
    }

    cpu = scx_bpf_select_cpu_dfl(p, prev_cpu, wake_flags, &is_idle);
    place_with_snapshot(p, 0, &dir, have_directive, fallback,
                        1, is_idle, cpu);
    return cpu;
}

void BPF_STRUCT_OPS(orchestra_sched_enqueue, struct task_struct *p,
                    u64 enq_flags)
{
    struct directive_snapshot dir = {};
    uint32_t fallback = BRIDGE_FALLBACK_NO_DIRECTIVE;
    int have_directive = load_directive(p, &dir, &fallback);
    struct bridge_telemetry *tel = global_tel();

    if (tel)
        tel_inc(&tel->enqueue_callback_count);
    place_with_snapshot(p, enq_flags, &dir, have_directive, fallback,
                        0, 0, -1);
}

void BPF_STRUCT_OPS(orchestra_sched_dispatch, s32 cpu,
                    struct task_struct *prev)
{
    struct bridge_telemetry *tel = global_tel();

    if (tel)
        tel_inc(&tel->dispatch_callback_count);
    /*
     * The core consumes SCX_DSQ_GLOBAL before invoking dispatch().
     * scx_bpf_consume() accepts only user-created non-local DSQs; passing
     * the reserved global ID is a runtime sched_ext error which detaches
     * the scheduler.  Deferred work is promoted by deferred_timerfn(), so
     * there is no custom DSQ for this callback to consume.
     */
    (void)cpu;
    (void)prev;
}

void BPF_STRUCT_OPS(orchestra_sched_running, struct task_struct *p)
{
    struct orchestra_task_identity id = task_identity(p);
    struct bridge_task_state *state = get_task_state(&id, 0);
    struct bridge_task_telemetry *task_tel = get_task_tel(&id, 0);
    struct bridge_telemetry *tel = global_tel();
    uint64_t now = bpf_ktime_get_ns();
    uint64_t telemetry_generation = 0;
    uint64_t state_generation = 0;
    uint64_t eligible_ns = 0;
    uint32_t action = ORCHESTRA_ACTION_RUN;
    uint32_t requested_cpu = ORCHESTRA_CPU_ANY;
    int32_t cpu = bpf_get_smp_processor_id();
    int migrate_target = 0;
    int migrate_other = 0;

    if (tel)
        tel_inc(&tel->running_count);
    if (!state || !task_tel)
        return;
    bpf_spin_lock(&state->lock);
    state_generation = state->generation;
    action = state->action;
    requested_cpu = state->requested_cpu;
    eligible_ns = state->eligible_ns;
    bpf_spin_unlock(&state->lock);
    bpf_spin_lock(&task_tel->lock);
    telemetry_generation = task_tel->generation;
    bpf_spin_unlock(&task_tel->lock);
    if (state_generation != telemetry_generation)
        return;
    bpf_spin_lock(&state->lock);
    state->running_since_ns = now;
    state->flags |= BRIDGE_TASK_F_RUNNING;
    bpf_spin_unlock(&state->lock);
    bpf_spin_lock(&task_tel->lock);
    task_tel->actual_cpu = cpu;
    task_tel->running_ns = now;
    task_tel->running_count++;

    switch (action) {
    case ORCHESTRA_ACTION_MIGRATE:
        if ((uint32_t)cpu == requested_cpu) {
            task_tel->effective_count++;
            migrate_target = 1;
        } else {
            task_tel->error_count++;
            migrate_other = 1;
        }
        break;
    case ORCHESTRA_ACTION_SLEEP:
        if (now < eligible_ns)
            task_tel->error_count++;
        break;
    case ORCHESTRA_ACTION_THROTTLE:
        break;
    case ORCHESTRA_ACTION_RUN:
    case ORCHESTRA_ACTION_YIELD:
        task_tel->effective_count++;
        break;
    default:
        task_tel->error_count++;
        break;
    }
    bpf_spin_unlock(&task_tel->lock);
    if (tel && migrate_target)
        tel_inc(&tel->migrate_running_target_count);
    if (tel && migrate_other)
        tel_inc(&tel->migrate_running_other_count);
}

void BPF_STRUCT_OPS(orchestra_sched_stopping, struct task_struct *p,
                    bool runnable)
{
    struct orchestra_task_identity id = task_identity(p);
    struct bridge_task_state *state = get_task_state(&id, 0);
    struct bridge_task_telemetry *task_tel = get_task_tel(&id, 0);
    struct bridge_telemetry *tel = global_tel();
    uint64_t now = bpf_ktime_get_ns();
    uint64_t delta = 0;
    uint64_t running_since = 0;

    if (tel)
        tel_inc(&tel->stopping_count);
    if (!state)
        return;
    bpf_spin_lock(&state->lock);
    if (!(state->flags & BRIDGE_TASK_F_RUNNING)) {
        bpf_spin_unlock(&state->lock);
        return;
    }
    running_since = state->running_since_ns;
    if (now >= running_since)
        delta = now - running_since;
    if (ORCHESTRA_U64_MAX - state->runtime_used_ns < delta)
        state->runtime_used_ns = ORCHESTRA_U64_MAX;
    else
        state->runtime_used_ns += delta;
    state->running_since_ns = 0;
    state->flags &= ~BRIDGE_TASK_F_RUNNING;
    bpf_spin_unlock(&state->lock);
    if (task_tel) {
        bpf_spin_lock(&task_tel->lock);
        task_tel->stopped_ns = now;
        if (ORCHESTRA_U64_MAX - task_tel->runtime_ns < delta)
            task_tel->runtime_ns = ORCHESTRA_U64_MAX;
        else
            task_tel->runtime_ns += delta;
        bpf_spin_unlock(&task_tel->lock);
    }
    (void)runnable;
}

SCX_OPS_DEFINE(orchestra_sched_ops,
    .select_cpu = (void *)orchestra_sched_select_cpu,
    .enqueue = (void *)orchestra_sched_enqueue,
    .dispatch = (void *)orchestra_sched_dispatch,
    .running = (void *)orchestra_sched_running,
    .stopping = (void *)orchestra_sched_stopping,
    .enable = (void *)orchestra_sched_enable,
    .disable = (void *)orchestra_sched_disable,
    .init = (void *)orchestra_sched_init,
    .exit = (void *)orchestra_sched_exit,
    .flags = SCX_OPS_KEEP_BUILTIN_IDLE | SCX_OPS_ENQ_LAST,
    .name = "orchestra_scx_stage7",
    .timeout_ms = 30000U);
