# Future partial opt-in `sched_ext` preparation

Status: **Exploratory design only**. This document proposes no kernel code and
does not change the userspace prototype's claim class. Linux remains the actual
scheduler for the current experiment.

## Scope and admission

Only explicitly opted-in `SCHED_EXT` tasks would enter a future ORCHESTRA
prototype. RT (`SCHED_FIFO`/`SCHED_RR`) and deadline tasks remain outside this
path, retain their Linux scheduling-class precedence, and never receive an
ORCHESTRA action. A watchdog must return opted-in tasks to the normal
`sched_ext` fallback path if the control plane, signal verification, or BPF
program is unhealthy.

## Action mapping

| ORCHESTRA request | Proposed `sched_ext` approximation | Required effective-outcome trace |
| --- | --- | --- |
| `RUN` | immediate local DSQ dispatch | enqueue and dispatch CPU |
| `SLEEP` | bounded deferred eligibility | defer start, wake, and actual dispatch |
| `MIGRATE` | topology- and NUMA-aware CPU selection | requested and actual CPU, rejection reason |
| `THROTTLE` | shorter slice or bounded utilization policy | requested/effective slice and runtime |
| `YIELD` | shortened slice and requeue | requeue and subsequent dispatch |

These are contracts to evaluate, not assertions that identical userspace calls
have equivalent kernel semantics.

## Signal and measurement path

The BPF scheduling hot path would read a bounded, versioned signal from BPF
maps. Signal construction, HMAC/key lifecycle, prediction, policy learning,
consensus, and the slower feedback controller remain in a userspace control
plane. The hot path must use fixed-size data, bounded loops only, no floating
point, no blocking, no dynamic allocation, and explicit stale/invalid-signal
fallback to ordinary `sched_ext` policy.

Tracepoints must measure requested action separately from effective outcome:
request sequence, requested CPU, selected CPU, enqueue, dispatch, migration
completion/failure, slice changes, defer/wake timing, and fallback reason.
Those traces—not a requested action—are the basis for a future effective-action
metric. The BPF maps must expose sequence, freshness, source/tier identity, and
verification status without letting unverified data influence dispatch.

## Safety gates before implementation

1. Define an opt-in ABI, task lifecycle, and rollback semantics in an ADR.
2. Establish watchdog failure tests and RT/deadline non-interference tests.
3. Use tracepoint evidence to validate each proposed action contract.
4. Move only bounded, calibrated parameters into maps; keep exploration and
   adaptation outside the dispatch path until a safety case exists.
5. Measure CPU selection, DSQ latency, map access, and fallback overhead on a
   test kernel before any performance claim.
