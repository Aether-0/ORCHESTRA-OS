# Paper CPU Metrics v3 Contract

`orchestra.paper_cpu.metrics/v3` is the append-only CSV contract for the
canonical paper-aligned userspace prototype. It has 66 columns in the exact
order declared by
[`paper_cpu_metrics_v3.json`](../../experiments/schemas/paper_cpu_metrics_v3.json).
Every row carries `metrics_schema=orchestra.paper_cpu.metrics/v3`; readers must
reject a different identifier, a truncated row, or a reordered header.

## Scope and claim boundary

Linux CFS/EEVDF remains the scheduler. Version 3 adds bounded observations of
what a userspace worker attempted and subsequently observed. It does not expose
kernel scheduling intent, final dispatch order, context-switch ownership,
durable placement, or CPU capacity allocation.

`S2_selected` is selected policy/directive agreement. Historical `S2` remains
an exact alias, so existing v2 semantics are unchanged.

`S2_effective` is **userspace action-attempt effectiveness based on observable
post-action outcomes, not kernel scheduler compliance**. It is not part of the
historical Q calculation. Neither S2 field proves scheduler performance.

## New v3 fields

The existing 40 v2 fields come first, followed by the prior v3 diagnostics
`metrics_schema`, `S3_global`, and experimental `S3_conditioned`. The remaining
23 fields are appended in this exact sequence:

```text
S2_selected
S2_effective
action_attempt_count
effective_action_success_count
action_error_count
migration_attempt_count
migration_valid_requested_cpu_count
migration_affinity_success_count
migration_observed_success_count
migration_observed_success_fraction
sleep_attempt_count
sleep_effective_success_count
sleep_effectiveness_fraction
requested_sleep_ns_total
observed_sleep_ns_total
yield_attempt_count
yield_call_success_count
yield_call_success_fraction
throttle_attempt_count
throttle_operation_success_count
throttle_operation_success_fraction
fallback_fraction
fallback_reason
```

The full contract has 66 columns. The JSON schema is authoritative
for type, unit, range, missing-value policy, aggregation level, semantics, and
claim limit of every column.

## Effectiveness rules

- `RUN`: bounded intended work completed without action error or fallback.
- `SLEEP`: operation completed and monotonic elapsed sleep is no more than
  1 ms short and no more than 250 ms long relative to its request.
- `MIGRATE`: requested CPU is valid and eligible, affinity succeeds, and a
  bounded later CPU observation equals the requested CPU. Affinity success by
  itself is insufficient.
- `THROTTLE`: the bounded local delay/reduced-work operation completed without
  error or fallback. This is not evidence of a CPU cap.
- `YIELD`: `sched_yield()` returned successfully without fallback or
  invalid-state error. It does not establish that another process ran.

The action-specific fractions are success count divided by that action's
attempt count. If the count is zero, their fraction is `1` to mean *not
applicable*, not measured success. `S2_effective` is `1` with zero eligible
workers and `0` when eligible workers exist but no current action attempt is
observed. `fallback_fraction` is `0` with zero eligible workers.

## Coherence and compatibility

`S3_global` is the historical global entropy metric and exactly aliases `S3`.
`S3_conditioned` is experimental state-conditioned action coherence: empty
cohorts carry no weight and singleton cohorts score 1. Q remains based on
historical `S1`, `S2`, `S3`, and `S4`.

V2 is still readable as a distinct historical contract. V2 and v3 rows must
not be pooled silently in an analysis: v2 cannot reconstruct effective-action
outcomes, and a v3 row with a v2 schema label (or the reverse) is invalid.
Use invocation-level observations as the unit of repetition; individual CSV
rows are repeated time samples within one invocation, not independent runs.

See [ADR 0004](../adr/0004-effective-userspace-action-metrics.md) for the
decision, safety rationale, per-worker enums, and migration plan.
