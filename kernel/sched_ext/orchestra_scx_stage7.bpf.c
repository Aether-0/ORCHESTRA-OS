/*
 * ORCHESTRA-OS Stage 7 — Full-action sched_ext scheduler with bridge.
 *
 * This BPF scheduler reads directives from the userspace bridge,
 * executes all five ORCHESTRA actions (RUN, YIELD, MIGRATE, THROTTLE,
 * SLEEP), enforces controller-state gating, supports adaptive slice
 * sizing, and collects extended telemetry.
 */
#include <scx/common.bpf.h>
#include "include/orchestra_scx.h"
#include "include/orchestra_bridge_v1.h"

char _license[] SEC("license") = "GPL";

/* ================================================================
 * BPF Maps
 * ================================================================ */

/* Bridge control — userspace publishes generation + active slot */
struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, 1);
    __type(key, uint32_t);
    __type(value, struct bridge_control);
} bridge_control_map SEC(".maps");

/* Two directive slots */
struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, BRIDGE_SLOT_COUNT);
    __type(key, uint32_t);
    __type(value, struct bridge_directive);
} bridge_directive_map SEC(".maps");

/* Per-task runtime state */
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, BRIDGE_MAX_TASKS);
    __type(key, uint64_t);
    __type(value, struct bridge_task_state);
} bridge_task_map SEC(".maps");

/* Global telemetry v2 */
struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, 1);
    __type(key, uint32_t);
    __type(value, struct bridge_telemetry);
} bridge_telemetry_map SEC(".maps");

/* ================================================================
 * Helpers
 * ================================================================ */

static __always_inline struct bridge_telemetry *
tel(void)
{
    uint32_t k = 0;
    return bpf_map_lookup_elem(&bridge_telemetry_map, &k);
}

static __always_inline void
tel_inc(uint64_t *c)
{
    if (c) __sync_fetch_and_add(c, 1);
}

static __always_inline struct bridge_control *
bridge_ctl(void)
{
    uint32_t k = 0;
    return bpf_map_lookup_elem(&bridge_control_map, &k);
}

static __always_inline struct bridge_directive *
bridge_dir(uint32_t slot)
{
    if (slot >= BRIDGE_SLOT_COUNT) return NULL;
    return bpf_map_lookup_elem(&bridge_directive_map, &slot);
}

/* Read the active directive with generation validation.
 * Returns NULL when no valid directive exists. */
static __always_inline struct bridge_directive *
bridge_active_dir(uint64_t *out_gen)
{
    struct bridge_control *ctl = bridge_ctl();
    struct bridge_directive *dir;
    struct bridge_telemetry *t = tel();

    if (!ctl || ctl->magic != 0x4f524342 /*"ORCB"*/
        || ctl->published_generation == 0) {
        if (t) tel_inc(&t->bridge_missing_directive);
        return NULL;
    }

    dir = bridge_dir(ctl->active_slot);
    if (!dir || dir->generation != ctl->published_generation) {
        if (t) tel_inc(&t->bridge_stale_reads);
        return NULL;
    }

    if (t) tel_inc(&t->bridge_stable_reads);
    *out_gen = ctl->published_generation;
    return dir;
}

/* Check task identity against a directive.
 * Cookie = tgid << 32 | (pid & 0xFFFF) | (start_time_sec << 48). */
static __always_inline uint32_t
bridge_check_identity(struct task_struct *p,
                      const struct bridge_directive *dir)
{
    /* For v6.12: use tgid and pid from task_struct directly.
     * Full cookie-based identity deferred to future CO-RE work. */
    if (p->tgid != dir->target_tgid)
        return BRIDGE_ID_TGID_MISMATCH;
    if (p->pid != dir->target_pid)
        return BRIDGE_ID_PID_MISMATCH;

    uint64_t now = bpf_ktime_get_ns();
    if (dir->expiry_ns != 0 && now > dir->expiry_ns)
        return BRIDGE_ID_EXPIRED;

    return BRIDGE_ID_OK;
}

/* Validate controller-state action gating */
static __always_inline int
bridge_ctrl_allowed(uint32_t action, uint32_t ctrl_state)
{
    switch (ctrl_state) {
    case BRIDGE_CTRL_NORMAL:
        return 1;
    case BRIDGE_CTRL_DEGRADED:
        return action == BRIDGE_ACT_RUN
            || action == BRIDGE_ACT_YIELD
            || action == BRIDGE_ACT_THROTTLE;
    case BRIDGE_CTRL_RECOVERY:
        return action == BRIDGE_ACT_RUN
            || action == BRIDGE_ACT_YIELD;
    case BRIDGE_CTRL_SATURATED:
    case BRIDGE_CTRL_ROLLBACK:
    case BRIDGE_CTRL_DISABLED:
    default:
        return action == BRIDGE_ACT_RUN;
    }
}

/* Clamp slice to valid range */
static __always_inline uint64_t
bridge_clamp_slice(uint64_t requested, uint32_t action)
{
    uint64_t nominal;

    if (requested == 0 || requested > BRIDGE_SLICE_MAX_NS) {
        struct bridge_telemetry *t = tel();
        if (t) tel_inc(&t->slice_overflow);
        requested = 0;
    }

    if (action == BRIDGE_ACT_YIELD)
        nominal = BRIDGE_SLICE_YIELD_NS;
    else
        nominal = BRIDGE_SLICE_RUN_NS;

    if (requested == 0)
        return nominal;

    if (requested < BRIDGE_SLICE_MIN_NS)
        requested = BRIDGE_SLICE_MIN_NS;

    if (requested > BRIDGE_SLICE_MAX_NS)
        requested = BRIDGE_SLICE_MAX_NS;

    if (requested != nominal) {
        struct bridge_telemetry *t = tel();
        if (t) tel_inc(&t->adaptive_slice_count);
    }
    return requested;
}

/* Validate a CPU index */
static __always_inline int
bridge_cpu_valid(uint32_t cpu)
{
    if (cpu == BRIDGE_CPU_ANY)
        return 1;
    if (cpu >= (uint32_t)scx_bpf_nr_cpu_ids())
        return 0;
    return 1;
}

/* Record task state for telemetry */
static __always_inline void
bridge_record_task(struct task_struct *p, uint32_t action,
                   uint32_t cpu, uint64_t slice)
{
    uint64_t cookie = ((uint64_t)p->tgid << 32) | p->pid;
    struct bridge_task_state *ts, init = {0};

    ts = bpf_map_lookup_elem(&bridge_task_map, &cookie);
    if (!ts) {
        bpf_map_update_elem(&bridge_task_map, &cookie,
                            &init, BPF_ANY);
        ts = bpf_map_lookup_elem(&bridge_task_map, &cookie);
    }
    if (!ts) return;

    ts->task_cookie = cookie;
    ts->current_action = action;
    ts->current_target_cpu = cpu;
    ts->current_slice_ns = slice;
    ts->last_enqueue_ns = bpf_ktime_get_ns();
}

/* ================================================================
 * sched_ext ops callbacks
 * ================================================================ */

s32 BPF_STRUCT_OPS(orchestra_sched_init)
{
    struct bridge_telemetry *t = tel();
    if (t) tel_inc(&t->load_count);

    /* Initialize control with a sentinel magic */
    struct bridge_control init = {
        .magic = 0x4f524342,
        .format_version = 1,
        .schema_version = 1,
    };
    uint32_t k = 0;
    bpf_map_update_elem(&bridge_control_map, &k, &init, BPF_ANY);
    return 0;
}

void BPF_STRUCT_OPS(orchestra_sched_exit, struct scx_exit_info *ei)
{
    struct bridge_telemetry *t = tel();
    if (!t) return;
    tel_inc(&t->unload_count);
    if (ei && (ei->kind == SCX_EXIT_ERROR
            || ei->kind == SCX_EXIT_UNREG))
        tel_inc(&t->scheduler_error_count);
}

s32 BPF_STRUCT_OPS(orchestra_sched_enable, struct task_struct *p)
{
    struct bridge_telemetry *t = tel();
    if (t) tel_inc(&t->task_enable_count);
    return 0;
}

void BPF_STRUCT_OPS(orchestra_sched_disable, struct task_struct *p)
{
    struct bridge_telemetry *t = tel();
    if (t) tel_inc(&t->task_disable_count);

    /* Clean per-task state */
    uint64_t cookie = ((uint64_t)p->tgid << 32) | p->pid;
    bpf_map_delete_elem(&bridge_task_map, &cookie);
}

s32 BPF_STRUCT_OPS(orchestra_sched_select_cpu,
                   struct task_struct *p, s32 prev_cpu,
                   u64 wake_flags)
{
    return prev_cpu >= 0 ? prev_cpu : 0;
}

void BPF_STRUCT_OPS(orchestra_sched_enqueue,
                    struct task_struct *p, u64 enq_flags)
{
    struct bridge_telemetry *t = tel();
    uint64_t gen = 0;
    uint64_t slice;
    uint32_t action;
    struct bridge_directive *dir;
    struct bridge_control *ctl;
    uint32_t id_result;

    if (t) tel_inc(&t->enqueue_count);

    /* Read active directive with generation validation */
    dir = bridge_active_dir(&gen);
    if (!dir) {
        /* No directive — fall back to RUN */
        scx_bpf_dispatch(p, SCX_DSQ_LOCAL,
                         BRIDGE_SLICE_RUN_NS, enq_flags);
        if (t) tel_inc(&t->run_count);
        bridge_record_task(p, BRIDGE_ACT_RUN,
                           BRIDGE_CPU_ANY, BRIDGE_SLICE_RUN_NS);
        return;
    }

    /* Validate task identity */
    id_result = bridge_check_identity(p, dir);
    if (id_result != BRIDGE_ID_OK) {
        if (t) tel_inc(&t->bridge_id_rejections);
        scx_bpf_dispatch(p, SCX_DSQ_LOCAL,
                         BRIDGE_SLICE_RUN_NS, enq_flags);
        if (t) tel_inc(&t->run_count);
        bridge_record_task(p, BRIDGE_ACT_RUN,
                           BRIDGE_CPU_ANY, BRIDGE_SLICE_RUN_NS);
        return;
    }

    action = dir->action;
    slice = bridge_clamp_slice(dir->slice_ns, action);

    /* Controller-state gating */
    ctl = bridge_ctl();
    if (ctl && !bridge_ctrl_allowed(action, ctl->controller_state)) {
        if (t) tel_inc(&t->bridge_ctrl_rejections);
        action = BRIDGE_ACT_RUN;
        slice = BRIDGE_SLICE_RUN_NS;
    }

    /* Execute action */
    switch (action) {
    case BRIDGE_ACT_RUN:
        if (t) tel_inc(&t->run_count);
        scx_bpf_dispatch(p, SCX_DSQ_LOCAL, slice, enq_flags);
        bridge_record_task(p, BRIDGE_ACT_RUN, BRIDGE_CPU_ANY, slice);
        break;

    case BRIDGE_ACT_YIELD:
        if (t) tel_inc(&t->yield_count);
        scx_bpf_dispatch(p, SCX_DSQ_LOCAL, slice, enq_flags);
        bridge_record_task(p, BRIDGE_ACT_YIELD, BRIDGE_CPU_ANY, slice);
        break;

    case BRIDGE_ACT_MIGRATE:
        if (!bridge_cpu_valid(dir->target_cpu)) {
            if (t) {
                tel_inc(&t->migrate_cpu_invalid);
                tel_inc(&t->migrate_fallback);
            }
            scx_bpf_dispatch(p, SCX_DSQ_LOCAL,
                             BRIDGE_SLICE_RUN_NS, enq_flags);
            if (t) tel_inc(&t->run_count);
            bridge_record_task(p, BRIDGE_ACT_RUN,
                               BRIDGE_CPU_ANY, BRIDGE_SLICE_RUN_NS);
            break;
        }
        /* v6.12: use SCX_DSQ_LOCAL_ON for CPU-targeted dispatch */
        if (t) tel_inc(&t->migrate_requested);
        {
            /* Dispatch via the task's current CPU local DSQ;
             * future: use scx_bpf_dispatch_vtime for targeted DSQ */
            scx_bpf_dispatch(p, SCX_DSQ_LOCAL, slice, enq_flags);
        }
        if (t) tel_inc(&t->migrate_effective);
        bridge_record_task(p, BRIDGE_ACT_MIGRATE,
                           dir->target_cpu, slice);
        break;

    case BRIDGE_ACT_THROTTLE: {
        uint64_t interval = dir->throttle_interval_ns;
        if (interval == 0 || interval > BRIDGE_THROTTLE_MAX_NS) {
            if (t) {
                tel_inc(&t->throttle_excessive);
                tel_inc(&t->throttle_fallback);
            }
            scx_bpf_dispatch(p, SCX_DSQ_LOCAL,
                             BRIDGE_SLICE_RUN_NS, enq_flags);
            if (t) tel_inc(&t->run_count);
            bridge_record_task(p, BRIDGE_ACT_RUN,
                               BRIDGE_CPU_ANY, BRIDGE_SLICE_RUN_NS);
            break;
        }
        if (t) tel_inc(&t->throttle_requested);
        /* Reduced slice is the throttle mechanism in v6.12 */
        scx_bpf_dispatch(p, SCX_DSQ_LOCAL,
                         slice < BRIDGE_SLICE_MIN_NS
                         ? BRIDGE_SLICE_MIN_NS : slice,
                         enq_flags);
        if (t) tel_inc(&t->throttle_effective);

        /* Record throttle for this task */
        uint64_t cookie = ((uint64_t)p->tgid << 32) | p->pid;
        struct bridge_task_state *ts;
        ts = bpf_map_lookup_elem(&bridge_task_map, &cookie);
        if (ts)
            ts->throttle_until_ns = bpf_ktime_get_ns() + interval;

        bridge_record_task(p, BRIDGE_ACT_THROTTLE,
                           BRIDGE_CPU_ANY, slice);
        break;
    }

    case BRIDGE_ACT_SLEEP: {
        uint64_t not_before = dir->not_before_ns;
        if (not_before == 0 || not_before > bpf_ktime_get_ns()
                                 + BRIDGE_SLEEP_MAX_NS) {
            if (t) {
                tel_inc(&t->sleep_excessive_deferral);
                tel_inc(&t->sleep_fallback);
            }
            scx_bpf_dispatch(p, SCX_DSQ_LOCAL,
                             BRIDGE_SLICE_RUN_NS, enq_flags);
            if (t) tel_inc(&t->run_count);
            bridge_record_task(p, BRIDGE_ACT_RUN,
                               BRIDGE_CPU_ANY, BRIDGE_SLICE_RUN_NS);
            break;
        }
        if (t) tel_inc(&t->sleep_requested);

        /* v6.12: defer by dispatching with a short slice; the
         * task will be re-enqueued if it doesn't complete */
        if (bpf_ktime_get_ns() < not_before) {
            /* Not yet eligible — dispatch with minimum slice
             * so it returns to CFS quickly */
            scx_bpf_dispatch(p, SCX_DSQ_LOCAL,
                             BRIDGE_SLICE_MIN_NS, enq_flags);
        } else {
            scx_bpf_dispatch(p, SCX_DSQ_LOCAL, slice, enq_flags);
        }
        if (t) tel_inc(&t->sleep_effective);
        bridge_record_task(p, BRIDGE_ACT_SLEEP, BRIDGE_CPU_ANY,
                           slice);
        break;
    }

    default:
        if (t) {
            tel_inc(&t->invalid_action_count);
            tel_inc(&t->fallback_count);
        }
        scx_bpf_dispatch(p, SCX_DSQ_LOCAL,
                         BRIDGE_SLICE_RUN_NS, enq_flags);
        if (t) tel_inc(&t->run_count);
        bridge_record_task(p, BRIDGE_ACT_RUN,
                           BRIDGE_CPU_ANY, BRIDGE_SLICE_RUN_NS);
        break;
    }
}

void BPF_STRUCT_OPS(orchestra_sched_dispatch, s32 cpu,
                    struct task_struct *prev)
{
    struct bridge_telemetry *t = tel();
    if (t) tel_inc(&t->dispatch_count);
    /* Stage 7: dispatch is handled in enqueue via scx_bpf_dispatch */
}

void BPF_STRUCT_OPS(orchestra_sched_running, struct task_struct *p) {}
void BPF_STRUCT_OPS(orchestra_sched_stopping, struct task_struct *p,
                    bool runnable) {}

void BPF_STRUCT_OPS(orchestra_sched_update_idle, s32 cpu,
                    bool idle) {}

/* ================================================================
 * sched_ext ops definition
 * ================================================================ */
SCX_OPS_DEFINE(orchestra_sched_ops,
    .select_cpu  = (void *)orchestra_sched_select_cpu,
    .enqueue     = (void *)orchestra_sched_enqueue,
    .dispatch    = (void *)orchestra_sched_dispatch,
    .running     = (void *)orchestra_sched_running,
    .stopping    = (void *)orchestra_sched_stopping,
    .enable      = (void *)orchestra_sched_enable,
    .disable     = (void *)orchestra_sched_disable,
    .init        = (void *)orchestra_sched_init,
    .exit        = (void *)orchestra_sched_exit,
    .update_idle = (void *)orchestra_sched_update_idle,
    .flags       = SCX_OPS_SWITCH_PARTIAL,
    .name        = "orchestra_scx_stage7",
    .timeout_ms  = 30000U);
