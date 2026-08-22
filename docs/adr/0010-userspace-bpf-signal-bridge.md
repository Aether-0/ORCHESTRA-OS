# Userspace-to-BPF Signal Bridge

Status: **Implemented**

## Problem statement

Stage 6 proved the sched_ext BPF scheduler could load, enable, and schedule opted-in tasks with RUN and YIELD. Stage 7 extends this to a two-way bridge: the userspace controller publishes validated directives and, when requested, a bounded fixed-point signal frame through versioned BPF maps; the BPF scheduler reads, validates, and executes all five ORCHESTRA actions with bounded behavior.

## Trust boundary

The userspace controller resides outside the kernel trust boundary. The BPF scheduler validates every directive read from userspace-populated maps:
- Bridge magic and schema version must match
- Generation must agree between control and directive maps
- Task identity (TGID + PID + start-time cookie) must match
- Directive must not have expired
- Controller state must permit the requested action

When a directive carries `BRIDGE_DIRECTIVE_F_REQUIRE_SIGNAL`, BPF also requires
an `orch_signal` frame with the expected ABI and exact value size, known flags,
matching scheduler/controller/policy epoch, non-zero increasing publication
metadata, bounded fixed-point values, and a current freshness window. The
bridge's `--stream` path publishes one signal frame before the associated
per-task directives and marks each directive as signal-required.

Invalid, stale, or unverifiable directives produce safe RUN fallback and telemetry only. No invalid directive may influence scheduler behavior beyond the fallback path.

The frame is a trusted local map transport. The userspace prototype still
performs canonical serialization and HMAC-SHA256 verification in its own
signal bus; this kernel prototype does not verify that HMAC and does not claim
cryptographic signal-bus validation.

## Bridge versioning

| Field | Value |
|-------|-------|
| Magic | `0x4f524342` ("ORCB") |
| Format version | 2 |
| Schema version | 2 |

All fields use fixed-width integer types and natural native alignment. No
pointers, floating point, or variable-length data appear in the bridge map
records. The fixed-point signal frame uses `BRIDGE_SIGNAL_SCALE=1000`.

## Map layouts

| Map | Type | Key | Value | Size | Purpose |
|-----|------|-----|-------|------|---------|
| `orch_control` | ARRAY | uint32=0 | `bridge_control` (80 B) | 1 | Scheduler epoch, lease, policy/controller state |
| `orch_directives` | HASH | task identity | `bridge_directive` (112 B) | 4096 | Per-task action directives |
| `orch_identity` | HASH | TGID/TID | `bridge_identity_record` (16 B) | 4096 | Current task lifetime identity |
| `orch_task_state` | HASH | task identity | `bridge_task_state` (72 B) | 4096 | Per-task runtime/deferred state |
| `orch_task_tel` | HASH | task identity | `bridge_task_telemetry` (104 B) | 4096 | Last action outcome |
| `orch_telemetry` | ARRAY | uint32=0 | `bridge_telemetry` (328 B) | 1 | Global callback/action/signal counters |
| `orch_defer_tmr` | ARRAY | uint32=0 | `bridge_defer_timer` (16 B) | 1 | Pinned BPF timer state |
| `orch_signal` | ARRAY | uint32=0 | `bridge_signal_frame` (152 B) | 1 | Bounded fixed-point signal/prediction/metric transport |

The canonical engine stream uses a 176-byte `bridge_stream_request`. Its
signal extension is optional per record; `BRIDGE_STREAM_F_PUBLISH_SIGNAL`
publishes the frame and `BRIDGE_STREAM_F_REQUIRE_SIGNAL` applies the fail-closed
directive gate.

## Two-slot publication

1. Userspace reads the control map and current scheduler epoch
2. The bridge validates and publishes the signal frame under `BPF_F_LOCK`
3. The bridge reads back every signal field and validates exact match
4. The bridge publishes a lifetime-identity directive with a new generation
5. The bridge reads back the directive, control lease, and identity
6. BPF snapshots control/directive coherently and validates the directive
7. A required-signal directive snapshots and validates `orch_signal` before it
   can influence dispatch

A partial or failed inactive-slot write never becomes active because the control generation is not advanced.

## Task identity

Three-component identity: TGID, PID, task start-time cookie (`/proc/[pid]/stat` field 22, `p->start_boottime` in BPF). Cookie zero disables the check for legacy compatibility. PID reuse is mitigated by the cookie: a new task with the same PID will have a different start time.

## Online policy loading

Reuses Stage 5 policy validator. Invalid policy preserves previous active generation. BPF never parses policy files.

## Action semantics

| Action | Implementation |
|--------|---------------|
| RUN | `scx_bpf_dsq_insert(p, SCX_DSQ_LOCAL, slice, flags)` |
| YIELD | RUN with nominal 1ms slice |
| MIGRATE | CPU validation, `SCX_DSQ_LOCAL_ON | target_cpu` insertion with target recording |
| THROTTLE | Reduced slice dispatch with per-task throttle-until timestamp |
| SLEEP | Deferred eligibility via `not_before_ns`; a successful timer release retires the exact generation to RUN |

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

- SLEEP is a one-shot eligibility transition, not a persistent sleep state: after the exact generation is released, its directive is retired to RUN; a newer generation remains authoritative
- Bridge maps must be individually pinned before scheduler attach when the
  deferred timer is used
- The fixed-point signal map has freshness and coherence validation but no
  kernel-side cryptographic authentication
- The privileged bridge refuses directives for current `SCHED_FIFO`,
  `SCHED_RR`, and `SCHED_DEADLINE` targets; this is an admission guard, not a
  complete kernel Hybrid Safety Layer or RT coexistence proof
- VirtualBox-only runtime validation; no bare-metal testing
