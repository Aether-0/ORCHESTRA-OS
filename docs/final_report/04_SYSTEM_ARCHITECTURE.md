# 4. System Architecture

## Three-Layer Design

```
┌──────────────────────────────────────────────────────┐
│                 LAYER A: USERSAPCE                    │
│  ┌──────────┐  ┌────────────┐  ┌──────────────────┐ │
│  │Predictor │→ │Controller  │→ │Policy Engine     │ │
│  │(EWMA)    │  │(6 states)  │  │(Q-table, TRAIN/   │ │
│  │          │  │            │  │ ADAPT/EVALUATE)   │ │
│  └──────────┘  └────────────┘  └──────────────────┘ │
│        │              │                  │            │
│        └──────────────┼──────────────────┘            │
│                       ↓                               │
│  ┌───────────────────────────────────────────────┐   │
│  │         Generation-Stamped Signal Bus         │   │
│  │    (C11 atomic, two-slot, 128B + 32B HMAC)   │   │
│  └───────────────────────────────────────────────┘   │
└───────────────────────┬───────────────────────────────┘
                        │ MAP_SHARED mmap
┌───────────────────────▼───────────────────────────────┐
│                 LAYER B: BRIDGE                        │
│  ┌───────────────────────────────────────────────┐   │
│  │  bridge_control (ARRAY, 1 entry)              │   │
│  │  bridge_directive (ARRAY, 2 slots)            │   │
│  │  bridge_task_state (HASH, 128 entries)        │   │
│  │  bridge_telemetry (ARRAY, 1 entry, 40 fields) │   │
│  └───────────────────────────────────────────────┘   │
│                                                       │
│  Userspace CLI: --publish, --dry-run, --clear         │
└───────────────────────┬───────────────────────────────┘
                        │ BPF maps (read from kernel)
┌───────────────────────▼───────────────────────────────┐
│                 LAYER C: KERNEL                        │
│  ┌───────────────────────────────────────────────┐   │
│  │           sched_ext ops callbacks              │   │
│  │  .init .exit .enable .disable .select_cpu     │   │
│  │  .enqueue .dispatch .running .stopping        │   │
│  │  .update_idle                                  │   │
│  └───────────────────────────────────────────────┘   │
│                                                       │
│  SCX_OPS_SWITCH_PARTIAL (only opted-in tasks)         │
│  SCX_DSQ_LOCAL dispatch                               │
└───────────────────────────────────────────────────────┘
```

## Data Flow

1. **Acquisition:** `/proc/stat`, `/proc/meminfo` → CPU, memory, thermal
2. **Prediction:** Fixed-gain EWMA → short-horizon CPU forecast
3. **Directive:** Controller state → policy action → bridge publication
4. **Dispatch:** BPF reads active slot → validates generation → executes action
5. **Telemetry:** 40 counters updated atomically in bridge_telemetry map

## Subsystem Interaction

| From | To | Mechanism |
|------|----|-----------|
| Predictor | Signal Bus | `serialize_payload()` + HMAC |
| Signal Bus | Workers | `mmap(MAP_SHARED)` read-only |
| Controller | Signal Bus | `controller_machine_update()` |
| Policy Engine | Bridge CLI | `policy_deserialize()` |
| Bridge CLI | BPF Maps | `bpf_map_update_elem()` |
| BPF Maps | sched_ext | `bpf_map_lookup_elem()` |
| sched_ext | Tasks | `scx_bpf_dispatch()` |

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Geometric mean for Q | Prevents zero-factor collapse |
| Two-slot publication | Eliminates torn reads |
| Packed bridge structs | Deterministic sizes userspace↔BPF |
| TGID+PID+cookie identity | Mitigates PID reuse |
| Userspace-only controller | BPF no floating point, no blocking |
| `SCX_OPS_SWITCH_PARTIAL` | Only opted-in tasks use ORCHESTRA |
