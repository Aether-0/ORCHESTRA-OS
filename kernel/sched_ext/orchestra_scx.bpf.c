/*
 * ORCHESTRA-OS Stage 6 sched_ext MVP — BPF scheduler program.
 *
 * This is a minimal sched_ext scheduler that implements only RUN and YIELD.
 * It uses a frozen deterministic policy, partial opt-in, and bounded
 * dispatch with no unbounded loops, no floating point, and no blocking.
 *
 * Build (from kernel/sched_ext/):
 *   clang -O2 -target bpf -g -c orchestra_scx.bpf.c -o orchestra_scx.bpf.o
 *
 * The resulting .bpf.o must be verified by the BPF verifier before loading.
 */

#include <scx/common.bpf.h>

#include "include/orchestra_scx.h"

char _license[] SEC("license") = "GPL";

/* --- BPF maps --- */

/* Read-only frozen policy table */
struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, ORCHESTRA_POLICY_TABLE_SIZE);
    __type(key, uint32_t);
    __type(value, struct orchestra_policy_entry);
} orchestra_policy_map SEC(".maps");

/* Per-task state (PID → task_state) */
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 4096);
    __type(key, pid_t);
    __type(value, struct orchestra_task_state);
} orchestra_task_state_map SEC(".maps");

/* Global telemetry counters (single entry, key=0) */
struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, 1);
    __type(key, uint32_t);
    __type(value, struct orchestra_telemetry);
} orchestra_telemetry_map SEC(".maps");

/* --- Helpers --- */

static __always_inline void
orchestra_telemetry_inc(uint64_t *counter)
{
    if (!counter)
        return;
    __sync_fetch_and_add(counter, 1);
}

static __always_inline struct orchestra_telemetry *
orchestra_telemetry_get(void)
{
    uint32_t key = 0;
    return bpf_map_lookup_elem(&orchestra_telemetry_map, &key);
}

static __always_inline enum orchestra_action
orchestra_lookup_action(uint32_t state)
{
    uint32_t key = state;
    struct orchestra_policy_entry *entry;

    if (state >= ORCHESTRA_POLICY_TABLE_SIZE)
        return ORCHESTRA_ACT_RUN;

    entry = bpf_map_lookup_elem(&orchestra_policy_map, &key);
    if (!entry)
        return ORCHESTRA_ACT_RUN;

    switch (entry->action) {
    case ORCHESTRA_ACT_RUN:
        return ORCHESTRA_ACT_RUN;
    case ORCHESTRA_ACT_YIELD:
        return ORCHESTRA_ACT_YIELD;
    default:
        return ORCHESTRA_ACT_RUN;
    }
}

static __always_inline void
orchestra_record_task_action(pid_t pid, enum orchestra_action action)
{
    struct orchestra_task_state *ts;
    struct orchestra_task_state init = {};

    ts = bpf_map_lookup_elem(&orchestra_task_state_map, &pid);
    if (!ts) {
        bpf_map_update_elem(&orchestra_task_state_map, &pid, &init, BPF_ANY);
        ts = bpf_map_lookup_elem(&orchestra_task_state_map, &pid);
        if (!ts)
            return;
    }
    ts->last_action = (uint32_t)action;
}

/* --- sched_ext ops --- */

s32 BPF_STRUCT_OPS(orchestra_sched_init)
{
    struct orchestra_telemetry *tel = orchestra_telemetry_get();
    if (tel)
        orchestra_telemetry_inc(&tel->load_count);
    return 0;
}

void BPF_STRUCT_OPS(orchestra_sched_exit, struct scx_exit_info *ei)
{
    struct orchestra_telemetry *tel = orchestra_telemetry_get();
    if (tel) {
        orchestra_telemetry_inc(&tel->unload_count);
        if (ei && (ei->kind == SCX_EXIT_ERROR ||
                   ei->kind == SCX_EXIT_UNREG))
            orchestra_telemetry_inc(&tel->scheduler_error_count);
    }
}

s32 BPF_STRUCT_OPS(orchestra_sched_enable, struct task_struct *p)
{
    struct orchestra_telemetry *tel = orchestra_telemetry_get();

    if (!orchestra_should_optin())
        return 0;

    if (tel)
        orchestra_telemetry_inc(&tel->task_enable_count);

    orchestra_record_task_action(p->pid, ORCHESTRA_ACT_RUN);

    return 0;
}

void BPF_STRUCT_OPS(orchestra_sched_disable, struct task_struct *p)
{
    struct orchestra_telemetry *tel = orchestra_telemetry_get();
    if (tel)
        orchestra_telemetry_inc(&tel->task_disable_count);
}

s32 BPF_STRUCT_OPS(orchestra_sched_select_cpu, struct task_struct *p,
                   s32 prev_cpu, u64 wake_flags)
{
    /* Simple: return the previous CPU; let the kernel balance.
     * Future stages add topology-aware selection. */
    (void)p;
    (void)wake_flags;
    return prev_cpu >= 0 ? prev_cpu : 0;
}

void BPF_STRUCT_OPS(orchestra_sched_enqueue, struct task_struct *p,
                    u64 enq_flags)
{
    struct orchestra_telemetry *tel = orchestra_telemetry_get();
    if (tel)
        orchestra_telemetry_inc(&tel->enqueue_count);

    /* Dispatch to the global DSQ */
    scx_bpf_dispatch(p, SCX_DSQ_GLOBAL, ORCHESTRA_SLICE_NS_DEFAULT, enq_flags);
}

void BPF_STRUCT_OPS(orchestra_sched_dispatch, s32 cpu,
                    struct task_struct *prev)
{
    struct orchestra_telemetry *tel = orchestra_telemetry_get();
    uint32_t state = 0;
    enum orchestra_action action;
    struct bpf_iter_scx_dsq it;

    if (tel)
        orchestra_telemetry_inc(&tel->dispatch_count);

    state = (uint32_t)(bpf_ktime_get_ns() / ORCHESTRA_SLICE_NS_DEFAULT)
            % ORCHESTRA_POLICY_TABLE_SIZE;
    action = orchestra_lookup_action(state);

    bpf_for_each(scx_dsq, p, SCX_DSQ_GLOBAL, 0) {
        orchestra_record_task_action(p->pid, action);

        switch (action) {
        case ORCHESTRA_ACT_RUN:
            if (tel)
                orchestra_telemetry_inc(&tel->run_count);
            scx_bpf_dispatch(p, SCX_DSQ_GLOBAL,
                             ORCHESTRA_SLICE_NS_DEFAULT, 0);
            break;
        case ORCHESTRA_ACT_YIELD:
            if (tel)
                orchestra_telemetry_inc(&tel->yield_count);
            scx_bpf_dispatch(p, SCX_DSQ_GLOBAL,
                             ORCHESTRA_SLICE_NS_YIELD, 0);
            break;
        default:
            if (tel) {
                orchestra_telemetry_inc(&tel->invalid_action_count);
                orchestra_telemetry_inc(&tel->fallback_count);
            }
            scx_bpf_dispatch(p, SCX_DSQ_GLOBAL,
                             ORCHESTRA_SLICE_NS_DEFAULT, 0);
            break;
        }
    }

    if (prev)
        scx_bpf_consume(0);

    (void)it;
    (void)cpu;
}

void BPF_STRUCT_OPS(orchestra_sched_running, struct task_struct *p)
{
    /* No-op for Stage 6: slice tracking not implemented yet */
    (void)p;
}

void BPF_STRUCT_OPS(orchestra_sched_stopping, struct task_struct *p,
                    bool runnable)
{
    /* No-op for Stage 6 */
    (void)p;
    (void)runnable;
}

void BPF_STRUCT_OPS(orchestra_sched_update_idle, s32 cpu, bool idle)
{
    /* Consume from global DSQ when a CPU becomes idle */
    if (idle)
        scx_bpf_consume(0);
    (void)cpu;
}

/* --- sched_ext ops definition --- */

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
               .name        = "orchestra_scx_stage6",
               .timeout_ms  = 5000U);
