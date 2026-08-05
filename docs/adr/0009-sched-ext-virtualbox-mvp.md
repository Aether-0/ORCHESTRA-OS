# sched_ext VirtualBox MVP

Status: **Implemented**

## Motivation

The ORCHESTRA-OS research program requires a controlled test environment for kernel-level sched_ext integration. Stage 6 uses VirtualBox to provide a safe, recoverable guest VM with a custom sched_ext-capable kernel, isolating kernel experiments from the host.

## Scope

Stage 6 delivers:
- Minimal ORCHESTRA sched_ext scheduler (RUN and YIELD only)
- Partial opt-in via SCHED_EXT policy
- Frozen deterministic policy
- Safe load/unload with fallback to CFS
- Bounded telemetry
- Reproducible VirtualBox evidence

Stage 6 does NOT deliver:
- Full five-action kernel scheduler
- Online learning in kernel
- Userspace-to-BPF signal bridge
- Production security or performance claims

## Partial opt-in

Only tasks that explicitly set `SCHED_EXT` scheduling policy use the ORCHESTRA
scheduler. All other system tasks remain on the Linux fair scheduler. This
preserves system stability and enables controlled A/B comparison.

## Frozen policy

Stage 6 uses a hardcoded 30-entry state→action lookup table embedded in
the BPF program. No floating point, no file I/O, no online learning inside
the kernel. The policy maps states 0..14 to RUN and 15..29 to YIELD.

Future stages will load policies exported by the Stage 5 EVALUATE mode.

## RUN semantics

- Select eligible CPU (same-CPU for now)
- Dispatch to global DSQ
- 5ms bounded slice
- Record requested and actual dispatch

## YIELD semantics

- Dispatch to global DSQ with 1ms slice
- Tail requeue ensures eventual progress
- Record yield action

## Fallback

Unknown actions fall back to RUN. Invalid policy metadata → loader reject.
Scheduler error → SCX_EXIT_ERROR → CFS fallback.

## BPF map layout

| Map | Type | Key | Value | Purpose |
|-----|------|-----|-------|---------|
| orchestra_policy_map | ARRAY | state_index | policy_entry | Frozen action lookup |
| orchestra_task_state_map | HASH | pid | task_state | Per-task action/fallback |
| orchestra_telemetry_map | ARRAY | 0 | telemetry | Aggregated counters |

## Limitations

- No SLEEP/MIGRATE/THROTTLE kernel implementations
- No NUMA-aware CPU selection
- Single fixed-slice, no adaptive slicing
- No signal verification in BPF (signal stays in userspace)
- VirtualBox-only validation; no bare-metal testing
- Root required for scheduler load
