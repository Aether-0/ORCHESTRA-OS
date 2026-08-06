# Userspace-to-BPF Signal Bridge

Status: **Implemented**

## Problem statement

Stage 6 proved the sched_ext BPF scheduler could load, enable, and schedule opted-in tasks with RUN and YIELD. Stage 7 extends this to a full two-way bridge: the userspace controller publishes validated directives through versioned BPF maps, and the BPF scheduler reads, validates, and executes all five ORCHESTRA actions with bounded behavior.

## Trust boundary

The userspace controller resides outside the kernel trust boundary. The BPF scheduler validates every directive read from userspace-populated maps:
- Bridge magic and schema version must match
- Generation must agree between control and directive maps
- Task identity (TGID + PID + start-time cookie) must match
- Directive must not have expired
- Controller state must permit the requested action

Invalid, stale, or unverifiable directives produce safe RUN fallback and telemetry only. No invalid directive may influence scheduler behavior beyond the fallback path.

## Bridge versioning

| Field | Value |
|-------|-------|
| Magic | `0x4f524342` ("ORCB") |
| Format version | 1 |
| Schema version | 1 |

All fields use fixed-width packed integer types. No pointers, no floating point, no ABI padding.

## Map layouts

| Map | Type | Key | Value | Size | Purpose |
|-----|------|-----|-------|------|---------|
| `bridge_control_` | ARRAY | uint32=0 | `bridge_control` | 1 | Generation, active slot, status |
| `bridge_directiv` | ARRAY | uint32=0..1 | `bridge_directive` | 2 | Two directive slots |
| `bridge_task_map` | HASH | uint64 cookie | `bridge_task_state` | 128 | Per-task runtime state |
| `bridge_telemetr` | ARRAY | uint32=0 | `bridge_telemetry` | 1 | 40-counter telemetry v2 |

## Two-slot publication

1. Userspace reads control map to determine inactive slot
2. All directive fields are written to the inactive slot
3. Userspace reads back every field and validates exact match
4. Control map generation is incremented (checked arithmetic)
5. Active slot is updated, generation published atomically
6. BPF reads control first, validates magic/schema/generation
7. BPF reads the active slot only when generation matches control

A partial or failed inactive-slot write never becomes active because the control generation is not advanced.

## Task identity

Three-component identity: TGID, PID, task start-time cookie (`/proc/[pid]/stat` field 22, `p->start_boottime` in BPF). Cookie zero disables the check for legacy compatibility. PID reuse is mitigated by the cookie: a new task with the same PID will have a different start time.

## Online policy loading

Reuses Stage 5 policy validator. Invalid policy preserves previous active generation. BPF never parses policy files.

## Action semantics

| Action | Implementation |
|--------|---------------|
| RUN | `scx_bpf_dispatch(p, SCX_DSQ_LOCAL, slice, flags)` |
| YIELD | RUN with nominal 1ms slice |
| MIGRATE | CPU validation, SCX_DSQ_LOCAL dispatch with target recording |
| THROTTLE | Reduced slice dispatch with per-task throttle-until timestamp |
| SLEEP | Deferred eligibility via not_before_ns; unsupported capability documented |

## Controller-state gating

| State | RUN | YIELD | MIGRATE | THROTTLE | SLEEP |
|-------|-----|-------|---------|----------|-------|
| NORMAL | allow | allow | allow | allow | allow |
| DEGRADED | allow | allow | reject | allow | reject |
| SATURATED | allow | reject | reject | reject | reject |
| ROLLBACK | RUN fallback | reject | reject | reject | reject |
| RECOVERY | allow | allow | reject | reject | reject |
| DISABLED | RUN only | reject | reject | reject | reject |

## Limitations

- SLEEP capability requires kernel support for deferred BPF task dispatch
- Bridge maps must be individually pinned after scheduler load
- No cryptographic authentication of bridge maps (local trust only)
- VirtualBox-only runtime validation; no bare-metal testing
