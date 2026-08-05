# ADR 0004: Effective Userspace Action Metrics

- Status: Accepted — implemented userspace telemetry; exploratory measurement semantics
- Date: 2026-08-04
- Decision class: Userspace implementation contract, not kernel scheduling evidence
- Evidence status: Deterministic unit and bounded integration coverage are required; any bounded v3 campaign is pipeline validation, not a scheduler-performance experiment
- Maturity scope: Single-host userspace prototype only
- Work packages: WP4 Adaptive Process Scheduling, WP5 Coordination Measurement and Feedback Control, WP6 Instrumentation, and WP7 Experimental Evaluation
- Related: ADR 0001, ADR 0002, ADR 0003
- Supersedes: The absence of action-outcome telemetry described in ADR 0001 sections 2.7 and 2.8; all other ADR 0001 metric and controller contracts remain unchanged
- Superseded by: None

## 1. Context

The original userspace CSV records an action selected by the adaptive policy.
That makes historical `S2` useful as a policy/directive agreement measure, but
it does not show whether the process attempted the requested userspace
operation, whether the operation returned an error, or whether a bounded
post-action observation is consistent with the requested operation.

The prototype still does not replace Linux CFS/EEVDF. A userspace process
cannot infer Linux's dispatch intent, prove that it ran immediately, prove that
another task ran after `sched_yield()`, or establish a lasting CPU placement or
CPU-capacity reduction. Treating selected action or successful affinity alone
as kernel scheduler compliance would overstate the evidence.

The decision therefore keeps selected-action compliance intact and adds a
separate, deliberately narrower observable outcome metric. This is an
instrumentation and experiment-contract change, not a Linux scheduler change.

## 2. Decision

### 2.1 Two separate metrics

`S2_selected` is the historical selected-action compliance metric:

```text
S2_selected = selected actions matching the valid directive / eligible workers
```

The historical `S2` column is retained unchanged and is an exact alias of
`S2_selected`. It measures policy/directive agreement only. It is not kernel
dispatch compliance.

`S2_effective` is a distinct observable outcome metric:

```text
S2_effective = effective_action_success_count / eligible workers
```

It is named **userspace action-attempt effectiveness based on observable
post-action outcomes, not kernel scheduler compliance**. It does not become a
component of the historical Q formula, so `Q = (S1*S2*S3*S4)^(1/4)` remains
unchanged.

For zero eligible workers, both `S2_selected` and `S2_effective` are `1`,
matching the historical vacuous population convention. When eligible workers
exist but no current action attempt was observed, `S2_effective` is `0`.
Rejected or stale frames never count as successful effective actions.

### 2.2 Per-worker bounded observability record

For the latest action in each current observation window, an eligible worker
coherently records:

- selected action;
- whether execution was attempted, succeeded, or failed;
- action error number;
- CPU before the action, requested CPU, and CPU observed afterwards;
- whether a requested migration was observed;
- requested and monotonic-observed sleep durations;
- yield and throttle attempt flags;
- bounded fallback reason; and
- bounded effective-action result.

The record uses the existing per-worker shared-memory synchronization contract;
readers consume a coherent snapshot rather than independent uncoordinated
fields. The CSV aggregates one latest record per eligible worker and does not
export PID-keyed telemetry or arbitrary worker strings.

The validated integral worker enums are:

| Field | Values |
| --- | --- |
| `action_attempt_result` | `NOT_ATTEMPTED=0`, `ATTEMPT_SUCCEEDED=1`, `ATTEMPT_FAILED=2` |
| `fallback_reason` | `NONE=0`, `NO_VALID_FRAME=1`, `LAST_KNOWN_GOOD_EXPIRED=2` |
| `effective_action_result` | `NOT_ATTEMPTED=0`, `SUCCESS=1`, `FALLBACK=2`, `INVALID_ACTION=3`, `ACTION_ERROR=4`, `UNDERSLEEP=5`, `EXCESSIVE_OVERSLEEP=6`, `MIGRATION_NOT_OBSERVED=7`, `INVALID_REQUESTED_CPU=8` |

The aggregate CSV encodes fallback reason as `NONE`, `NO_VALID_FRAME`,
`LAST_KNOWN_GOOD_EXPIRED`, or `MULTIPLE` when eligible workers expose more than
one current reason.

### 2.3 Conservative action-specific effectiveness rules

All timing uses `CLOCK_MONOTONIC`. A frame that did not pass the normal
verification and freshness path cannot create a successful effective action.

| Selected action | Effective only when | Explicit limitation |
| --- | --- | --- |
| `RUN` | the bounded intended work path completed with no action-specific error or fallback | This does not prove immediate or uninterrupted Linux dispatch. |
| `SLEEP` | the sleep operation completed, observed elapsed time is at least requested duration minus 1 ms, and no more than requested duration plus 250 ms | It measures elapsed userspace wall time, not a kernel wake-up or dispatch guarantee. |
| `MIGRATE` | the requested CPU is valid and eligible, the affinity operation succeeds, and a bounded later CPU observation equals the requested CPU | Affinity success alone is insufficient. An already-target CPU can satisfy the observation condition but does not prove a migration transition or durable placement. |
| `THROTTLE` | the program applied its bounded reduced-work and/or delay operation without fallback or action error | This is **throttle-operation effectiveness**, not verified CPU-capacity reduction. |
| `YIELD` | `sched_yield()` returned successfully with no fallback or invalid-state error | It does not prove a context switch, fairness outcome, or that another process ran. |

Sleep requests and recorded observed duration are bounded. Under-sleep and
excessive oversleep have distinct effective-result values so an apparently
successful system call cannot silently count as an effective bounded sleep.

### 2.4 Aggregate v3 telemetry and zero denominators

`orchestra.paper_cpu.metrics/v3` has a strict 66-column ordered header. It
retains the 40 v2 columns and the prior append-only `metrics_schema`,
`S3_global`, and experimental `S3_conditioned` fields. It then appends action
attempt counts, effective-success/error counts, migration stages, sleep totals,
yield/throttle results, fallback fraction, and aggregate fallback reason.

Action-specific fractions use their corresponding attempt count. If an action
was not attempted, its fraction is `1` to represent *not applicable*, not a
measured successful operation; consumers must inspect its attempt count.
`fallback_fraction` is `fallback_workers / eligible_workers` when eligible
workers exist and `0` otherwise. All normalized fields are finite and in
`[0, 1]`.

The following population invariants are checked by the schema validator:

```text
S2 == S2_selected
effective_action_success_count + action_error_count <= action_attempt_count <= eligible_workers
migration_observed_success_count <= migration_affinity_success_count
  <= migration_valid_requested_cpu_count <= migration_attempt_count
each action-specific success count <= its attempt count <= eligible_workers
fallback_workers <= eligible_workers
```

`S3_global` remains the historical global entropy metric and `S3_conditioned`
remains an experimental diagnostic based on the userspace policy state ID.
Neither is redefined by this ADR.

### 2.5 Frame rejection and fallback behavior

Invalid, stale, or otherwise non-current frames remain telemetry-only. They do
not create a new adaptive decision, Q update, consensus operation, controller
update, or successful effective action. A bounded last-known-good record may
remain in use only under its existing safety window. Once unavailable or
expired, the worker records the bounded userspace fallback and its reason.

This behavior is intentionally operationally safe without suggesting that
userspace can hand control back to a scheduler it never replaced.

## 3. Alternatives Considered

### Keep selected action as the only S2 meaning

Rejected. It hides failed affinity requests, failed yields, sleep timing
deviations, and fallback activation behind a policy selection count.

### Call successful affinity a completed migration

Rejected. `sched_setaffinity()` constrains future eligibility; it does not by
itself show that the worker executed on the requested CPU.

### Treat `sched_yield()` success as proof that another process ran

Rejected. The return value provides no such observation to this prototype.

### Treat throttle operation as a verified CPU cap

Rejected. A self-imposed delay or smaller work quantum does not observe the
CPU capacity Linux ultimately granted to the task.

### Replace historical S2 or add S2_effective to Q

Rejected. Reinterpreting v2 would invalidate historical evidence. Adding a
new factor to Q would change its definition and require a separate metric
revision, comparability analysis, and evidence.

### Obtain kernel tracepoints from the default userspace path

Deferred. That would require a distinct privilege, trust, interface, and
measurement design. Default tests remain unprivileged.

## 4. Scientific and Engineering Evidence

The implementation exposes deterministic outcome classification over bounded
action-observation records, so unit tests can cover operation success, error,
invalid request, undersleep, oversleep, and unobserved migration paths without
relying on host migration timing. Short integration checks may exercise real
affinity, but host affinity restrictions are recorded as unavailable or failed
observations rather than converted into success.

The bounded v3 manifest and runner verify schema/header identity, row count,
hashes, environment, failed invocations, and invocation-level summaries. Such
a campaign validates the data pipeline only. It does not establish a causal
scheduler-performance effect, a Linux scheduler improvement, or a general
action-effectiveness rate.

## 5. Safety and Security Implications

- New worker state uses bounded integral values and counters rather than raw
  strings or unvalidated errno text.
- The parent aggregates only coherent per-worker snapshots; a metric race is
  treated as a research-validity defect rather than benign telemetry loss.
- HMAC, schema, source/tier, sequence, and freshness checks remain prerequisites
  for a new adaptive decision.
- No privileged scheduler class is enabled by this telemetry. `SCHED_FIFO` is
  not required for normal tests.
- Effective outcomes are recorded conservatively. Ambiguous outcomes are not
  silently upgraded to success.

## 6. Performance Implications

The change adds bounded shared-state stores, snapshot loads, monotonic clock
reads, and small per-publication aggregate calculations. It does not add an
unbounded wait, allocation, kernel hook, or group coordinator. The effects on
userspace load and timing must be measured separately; the telemetry is not a
license to describe the prototype as a scheduler hot path or to claim an
overhead budget.

## 7. Compatibility and Migration Plan

Historical v2 files remain readable under
`orchestra.paper_cpu.metrics/v2`, retain their original 40-column meanings,
and must not be edited. v3 readers require the schema identifier and exact
66-column order; a v2 row falsely labeled as v3, or a v3 row falsely labeled
as v2, is invalid.

Statistical summaries must not pool v2 and v3 observations. To compare an old
protocol with v3, rerun it under a v3 manifest and summarize each invocation
rather than treating individual rows as independent repetitions. The v3
fallback and action-attempt fields have no backfill for v2 artifacts.

Rollback is a clean rebuild that emits the historical v2 contract under its
own manifest and schema. It must not write a v2 identifier on a 66-column row.

## 8. Status and Superseding ADRs

This ADR is accepted for the single-host userspace prototype. It documents a
bounded observability contract and explicit claim limits; it does not provide
kernel scheduler integration, hard-real-time behavior, a complete fallback
mechanism, performance validation, or deployment readiness.

It supersedes only the listed action-outcome telemetry omissions in ADR 0001.
ADR 0001's directive, reward, Q, controller, and historical S1--S4 contracts
remain in force. Any change to effectiveness thresholds, enum values,
zero-denominator behavior, CSV column order, or the meaning of either S2 field
requires a new ADR and schema version review.
