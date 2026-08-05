#include <scx/common.bpf.h>
#include "include/orchestra_scx.h"

char _license[] SEC("license") = "GPL";

struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, ORCHESTRA_POLICY_TABLE_SIZE);
    __type(key, uint32_t);
    __type(value, struct orchestra_policy_entry);
} orchestra_policy_map SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 4096);
    __type(key, pid_t);
    __type(value, struct orchestra_task_state);
} orchestra_task_state_map SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, 1);
    __type(key, uint32_t);
    __type(value, struct orchestra_telemetry);
} orchestra_telemetry_map SEC(".maps");

static __always_inline struct orchestra_telemetry *orchestra_telemetry_get(void)
{
    uint32_t key = 0;
    return bpf_map_lookup_elem(&orchestra_telemetry_map, &key);
}

static __always_inline void orchestra_telemetry_inc(uint64_t *counter)
{
    if (counter) __sync_fetch_and_add(counter, 1);
}

s32 BPF_STRUCT_OPS(orchestra_sched_init)
{
    struct orchestra_telemetry *tel = orchestra_telemetry_get();
    if (tel) orchestra_telemetry_inc(&tel->load_count);
    return 0;
}

void BPF_STRUCT_OPS(orchestra_sched_exit, struct scx_exit_info *ei)
{
    struct orchestra_telemetry *tel = orchestra_telemetry_get();
    if (tel) {
        orchestra_telemetry_inc(&tel->unload_count);
        if (ei && (ei->kind == SCX_EXIT_ERROR || ei->kind == SCX_EXIT_UNREG))
            orchestra_telemetry_inc(&tel->scheduler_error_count);
    }
}

s32 BPF_STRUCT_OPS(orchestra_sched_enable, struct task_struct *p)
{
    struct orchestra_telemetry *tel = orchestra_telemetry_get();
    if (tel) orchestra_telemetry_inc(&tel->task_enable_count);
    return 0;
}

void BPF_STRUCT_OPS(orchestra_sched_disable, struct task_struct *p)
{
    struct orchestra_telemetry *tel = orchestra_telemetry_get();
    if (tel) orchestra_telemetry_inc(&tel->task_disable_count);
}

s32 BPF_STRUCT_OPS(orchestra_sched_select_cpu, struct task_struct *p,
                   s32 prev_cpu, u64 wake_flags)
{
    return prev_cpu >= 0 ? prev_cpu : 0;
}

void BPF_STRUCT_OPS(orchestra_sched_enqueue, struct task_struct *p, u64 enq_flags)
{
    struct orchestra_telemetry *tel = orchestra_telemetry_get();
    if (tel) orchestra_telemetry_inc(&tel->enqueue_count);
    scx_bpf_dispatch(p, SCX_DSQ_LOCAL, ORCHESTRA_SLICE_NS_DEFAULT, enq_flags);
}

void BPF_STRUCT_OPS(orchestra_sched_dispatch, s32 cpu, struct task_struct *prev)
{
    struct orchestra_telemetry *tel = orchestra_telemetry_get();
    if (tel) orchestra_telemetry_inc(&tel->dispatch_count);
}

void BPF_STRUCT_OPS(orchestra_sched_running, struct task_struct *p) {}
void BPF_STRUCT_OPS(orchestra_sched_stopping, struct task_struct *p, bool runnable) {}

void BPF_STRUCT_OPS(orchestra_sched_update_idle, s32 cpu, bool idle)
{
    
}

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
    .name        = "orchestra_scx_stage6",
    .timeout_ms  = 5000U);
