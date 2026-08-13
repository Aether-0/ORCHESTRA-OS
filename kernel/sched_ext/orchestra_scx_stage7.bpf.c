/*
 * ORCHESTRA-OS Stage 7 — Full-action sched_ext scheduler with bridge.
 *
 * This BPF scheduler reads directives from the userspace bridge,
 * executes all five ORCHESTRA actions (RUN, YIELD, MIGRATE, THROTTLE,
 * SLEEP), enforces controller-state gating, supports adaptive slice
 * sizing, and collects extended telemetry.
 *
 * P0 (known_recommand_fix.md):
 *   - SCX_OPS_SWITCH_PARTIAL is retained (CFS remains default).
 *     Workloads must sched_setattr(SCHED_EXT) or enqueue/run stay 0.
 *   - Default RUN / identity mismatch uses a fast path (no task-map write,
 *     cached directive generation).
 *   - .running counts actual SCX execution (ownership proof).
 *   - .dispatch is idle-callback telemetry only (idle_dispatch_count).
 *   - MIGRATE uses SCX_DSQ_LOCAL_ON | cpu (not SCX_DSQ_LOCAL).
 *
 * SLEEP/THROTTLE still cannot park a task in a custom DSQ: scx_bpf_consume
 * previously failed verification/kfunc mask on this 6.12 path. SLEEP holds
 * by skipping local dispatch only while ineligible is unsafe (lost task),
 * so SLEEP uses min-slice deferral until not_before; THROTTLE uses min slice.
 */
#include <scx/common.bpf.h>
#include "include/orchestra_scx.h"
#include "include/orchestra_bridge_v1.h"

char _license[] SEC("license") = "GPL";

#ifndef SCX_DSQ_LOCAL_ON
#define SCX_DSQ_LOCAL_ON (SCX_DSQ_FLAG_BUILTIN | SCX_DSQ_FLAG_LOCAL_ON)
#endif

/* Sample task-map writes 1/64 on the default RUN path. */
#define BRIDGE_TASK_SAMPLE_MASK 63u

/* ================================================================
 * BPF Maps
 * ================================================================ */

struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, 1);
    __type(key, uint32_t);
    __type(value, struct bridge_control);
} bridge_control_map SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, BRIDGE_SLOT_COUNT);
    __type(key, uint32_t);
    __type(value, struct bridge_directive);
} bridge_directive_map SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, BRIDGE_MAX_TASKS);
    __type(key, uint64_t);
    __type(value, struct bridge_task_state);
} bridge_task_map SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, 1);
    __type(key, uint32_t);
    __type(value, struct bridge_telemetry);
} bridge_telemetry_map SEC(".maps");

/* Cached active directive — skip full re-parse when generation is unchanged. */
struct dir_cache {
    uint64_t gen;
    uint32_t pid;
    uint32_t tgid;
    uint32_t action;
    uint32_t cpu;
    uint32_t ctrl_state;
    uint32_t valid;
    uint64_t slice;
    uint64_t not_before;
    uint64_t throttle;
    uint64_t cookie;
    uint64_t expiry;
};

struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, 1);
    __type(key, uint32_t);
    __type(value, struct dir_cache);
} dir_cache_map SEC(".maps");

static __always_inline struct dir_cache *
get_dir_cache(void)
{
    uint32_t k = 0;
    return bpf_map_lookup_elem(&dir_cache_map, &k);
}

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

/*
 * Refresh g_dir_cache from control+slot maps.
 * Returns 1 if a valid directive is cached, 0 otherwise.
 * On cache hit (same generation), skips the directive map lookup and
 * does not increment bridge_stable_reads.
 */
static __always_inline int
bridge_refresh_cache(struct dir_cache *c, struct bridge_telemetry *t)
{
    struct bridge_control *ctl = bridge_ctl();
    struct bridge_directive *dir;

    if (!c)
        return 0;

    if (!ctl || ctl->magic != 0x4f524342 /*"ORCB"*/
        || ctl->published_generation == 0) {
        c->valid = 0;
        if (t) tel_inc(&t->bridge_missing_directive);
        return 0;
    }

    if (c->valid && c->gen == ctl->published_generation)
        return 1;

    dir = bridge_dir(ctl->active_slot);
    if (!dir || dir->generation != ctl->published_generation) {
        c->valid = 0;
        if (t) tel_inc(&t->bridge_stale_reads);
        return 0;
    }

    c->gen = ctl->published_generation;
    c->pid = dir->target_pid;
    c->tgid = dir->target_tgid;
    c->action = dir->action;
    c->cpu = dir->target_cpu;
    c->slice = dir->slice_ns;
    c->not_before = dir->not_before_ns;
    c->throttle = dir->throttle_interval_ns;
    c->cookie = dir->task_cookie;
    c->expiry = dir->expiry_ns;
    c->ctrl_state = ctl->controller_state;
    c->valid = 1;
    if (t) tel_inc(&t->bridge_stable_reads);
    return 1;
}

static __always_inline uint32_t
bridge_check_identity_cached(struct task_struct *p, const struct dir_cache *c)
{
    if (!c)
        return BRIDGE_ID_STALE_GEN;
    if (p->tgid != c->tgid)
        return BRIDGE_ID_TGID_MISMATCH;
    if (p->pid != c->pid)
        return BRIDGE_ID_PID_MISMATCH;

    /* Cookie 0 = do not check (userspace /proc starttime != start_boottime). */
    if (c->cookie != 0 && p->start_boottime != c->cookie)
        return BRIDGE_ID_COOKIE_MISMATCH;

    if (c->expiry != 0 && bpf_ktime_get_ns() > c->expiry)
        return BRIDGE_ID_EXPIRED;

    return BRIDGE_ID_OK;
}

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

static __always_inline uint64_t
bridge_clamp_slice(uint64_t requested, uint32_t action)
{
    uint64_t nominal;

    if (requested == 0 || requested > BRIDGE_SLICE_MAX_NS) {
        struct bridge_telemetry *t = tel();
        if (requested > BRIDGE_SLICE_MAX_NS && t)
            tel_inc(&t->slice_overflow);
        requested = 0;
    }

    if (action == BRIDGE_ACT_YIELD)
        nominal = BRIDGE_SLICE_YIELD_NS;
    else if (action == BRIDGE_ACT_THROTTLE)
        nominal = BRIDGE_SLICE_MIN_NS;
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

static __always_inline int
bridge_cpu_valid(uint32_t cpu)
{
    if (cpu == BRIDGE_CPU_ANY)
        return 1;
    if (cpu >= (uint32_t)scx_bpf_nr_cpu_ids())
        return 0;
    return 1;
}

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

static __always_inline void
fast_run(struct task_struct *p, u64 enq_flags, struct bridge_telemetry *t)
{
    scx_bpf_dispatch(p, SCX_DSQ_LOCAL, BRIDGE_SLICE_RUN_NS, enq_flags);
    if (t) {
        tel_inc(&t->run_count);
        tel_inc(&t->fastpath_run_count);
    }
}

/* ================================================================
 * sched_ext ops callbacks
 * ================================================================ */

s32 BPF_STRUCT_OPS(orchestra_sched_init)
{
    struct bridge_telemetry *t = tel();
    if (t) tel_inc(&t->load_count);

    struct bridge_control init = {
        .magic = 0x4f524342,
        .format_version = 1,
        .schema_version = 1,
    };
    uint32_t k = 0;
    bpf_map_update_elem(&bridge_control_map, &k, &init, BPF_ANY);
    {
        struct dir_cache *c = get_dir_cache();
        if (c)
            c->valid = 0;
    }
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

    uint64_t cookie = ((uint64_t)p->tgid << 32) | p->pid;
    bpf_map_delete_elem(&bridge_task_map, &cookie);
}

static __always_inline void
orchestra_place(struct task_struct *p, u64 enq_flags)
{
    struct bridge_telemetry *t = tel();
    uint64_t slice;
    uint32_t action;
    uint32_t id_result;
    struct dir_cache *c = get_dir_cache();

    if (t) tel_inc(&t->enqueue_count);

    if (!c || !bridge_refresh_cache(c, t)) {
        fast_run(p, enq_flags, t);
        return;
    }

    id_result = bridge_check_identity_cached(p, c);
    if (id_result != BRIDGE_ID_OK) {
        if (t) tel_inc(&t->bridge_id_rejections);
        fast_run(p, enq_flags, t);
        return;
    }

    action = c->action;
    slice = bridge_clamp_slice(c->slice, action);

    if (!bridge_ctrl_allowed(action, c->ctrl_state)) {
        if (t) tel_inc(&t->bridge_ctrl_rejections);
        action = BRIDGE_ACT_RUN;
        slice = BRIDGE_SLICE_RUN_NS;
    }

    switch (action) {
    case BRIDGE_ACT_RUN:
        if (t) tel_inc(&t->run_count);
        scx_bpf_dispatch(p, SCX_DSQ_LOCAL, slice, enq_flags);
        if (t && (t->enqueue_count & BRIDGE_TASK_SAMPLE_MASK) == 1)
            bridge_record_task(p, BRIDGE_ACT_RUN, BRIDGE_CPU_ANY, slice);
        break;

    case BRIDGE_ACT_YIELD:
        if (t) tel_inc(&t->yield_count);
        scx_bpf_dispatch(p, SCX_DSQ_LOCAL, BRIDGE_SLICE_YIELD_NS, enq_flags);
        bridge_record_task(p, BRIDGE_ACT_YIELD, BRIDGE_CPU_ANY,
                           BRIDGE_SLICE_YIELD_NS);
        break;

    case BRIDGE_ACT_MIGRATE:
        if (!bridge_cpu_valid(c->cpu)
            || c->cpu == BRIDGE_CPU_ANY) {
            if (t) {
                tel_inc(&t->migrate_cpu_invalid);
                tel_inc(&t->migrate_fallback);
            }
            fast_run(p, enq_flags, t);
            break;
        }
        if (t) tel_inc(&t->migrate_requested);
        scx_bpf_dispatch(p, SCX_DSQ_LOCAL_ON | c->cpu,
                         slice, enq_flags);
        scx_bpf_kick_cpu((s32)c->cpu, 0);
        if (t) tel_inc(&t->migrate_effective);
        bridge_record_task(p, BRIDGE_ACT_MIGRATE, c->cpu, slice);
        break;

    case BRIDGE_ACT_THROTTLE: {
        uint64_t interval = c->throttle;
        uint64_t thr_slice;

        if (interval == 0 || interval > BRIDGE_THROTTLE_MAX_NS) {
            if (t) {
                tel_inc(&t->throttle_excessive);
                tel_inc(&t->throttle_fallback);
            }
            fast_run(p, enq_flags, t);
            break;
        }
        if (t) tel_inc(&t->throttle_requested);
        thr_slice = slice < BRIDGE_SLICE_MIN_NS ? BRIDGE_SLICE_MIN_NS : slice;
        if (thr_slice > BRIDGE_SLICE_MIN_NS)
            thr_slice = BRIDGE_SLICE_MIN_NS;
        scx_bpf_dispatch(p, SCX_DSQ_LOCAL, thr_slice, enq_flags);
        if (t) tel_inc(&t->throttle_effective);
        {
            uint64_t cookie = ((uint64_t)p->tgid << 32) | p->pid;
            struct bridge_task_state *ts;
            ts = bpf_map_lookup_elem(&bridge_task_map, &cookie);
            if (ts)
                ts->throttle_until_ns = bpf_ktime_get_ns() + interval;
        }
        bridge_record_task(p, BRIDGE_ACT_THROTTLE, BRIDGE_CPU_ANY, thr_slice);
        break;
    }

    case BRIDGE_ACT_SLEEP: {
        uint64_t not_before = c->not_before;
        uint64_t now = bpf_ktime_get_ns();

        if (not_before == 0 || not_before > now + BRIDGE_SLEEP_MAX_NS) {
            if (t) {
                tel_inc(&t->sleep_excessive_deferral);
                tel_inc(&t->sleep_fallback);
            }
            fast_run(p, enq_flags, t);
            break;
        }
        if (t) tel_inc(&t->sleep_requested);
        if (now < not_before) {
            scx_bpf_dispatch(p, SCX_DSQ_LOCAL,
                             BRIDGE_SLICE_MIN_NS, enq_flags);
        } else {
            scx_bpf_dispatch(p, SCX_DSQ_LOCAL, slice, enq_flags);
            if (t) tel_inc(&t->sleep_effective);
        }
        bridge_record_task(p, BRIDGE_ACT_SLEEP, BRIDGE_CPU_ANY, slice);
        break;
    }

    default:
        if (t) {
            tel_inc(&t->invalid_action_count);
            tel_inc(&t->fallback_count);
        }
        fast_run(p, enq_flags, t);
        break;
    }
}

s32 BPF_STRUCT_OPS(orchestra_sched_select_cpu,
                   struct task_struct *p, s32 prev_cpu,
                   u64 wake_flags)
{
    struct dir_cache *c = get_dir_cache();
    s32 cpu = prev_cpu >= 0 ? prev_cpu : 0;

    (void)wake_flags;
    if (c && c->valid
        && c->action == BRIDGE_ACT_MIGRATE
        && p->pid == c->pid
        && c->cpu != BRIDGE_CPU_ANY
        && bridge_cpu_valid(c->cpu))
        cpu = (s32)c->cpu;

    /* Direct-dispatch here so wakeups are not inserted by the core
     * without running the action path (enqueue is then skipped). */
    orchestra_place(p, 0);
    return cpu;
}

void BPF_STRUCT_OPS(orchestra_sched_enqueue,
                    struct task_struct *p, u64 enq_flags)
{
    orchestra_place(p, enq_flags);
}

void BPF_STRUCT_OPS(orchestra_sched_dispatch, s32 cpu,
                    struct task_struct *prev)
{
    struct bridge_telemetry *t = tel();
    if (t) {
        tel_inc(&t->dispatch_count);
        tel_inc(&t->idle_dispatch_count);
    }
    /* Inserts happen in enqueue. This callback is idle-path noise. */
}

void BPF_STRUCT_OPS(orchestra_sched_running, struct task_struct *p)
{
    struct bridge_telemetry *t = tel();
    if (t) tel_inc(&t->running_count);
}

void BPF_STRUCT_OPS(orchestra_sched_stopping, struct task_struct *p,
                    bool runnable) {}

void BPF_STRUCT_OPS(orchestra_sched_update_idle, s32 cpu,
                    bool idle) {}

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
    .flags       = SCX_OPS_SWITCH_PARTIAL | SCX_OPS_ENQ_LAST,
    .name        = "orchestra_scx_stage7",
    .timeout_ms  = 30000U);
