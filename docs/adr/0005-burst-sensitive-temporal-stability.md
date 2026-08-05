# ADR 0005: Experimental burst-sensitive temporal stability

- Status: Accepted for the paper-aligned userspace prototype
- Date: 2026-08-04
- Work package: WP5 Coordination Measurement and Feedback Control
- Claim class: Exploratory metric implemented in a userspace-validated prototype

## 1. Context

The historical temporal-stability component remains deliberately unchanged:

~~~text
S4 = 1 - changed_eligible_workers / eligible_workers
~~~

It is 1 for zero eligible workers. Historical S4 is bounded and comparable with
v2/v3 evidence, but it penalizes an isolated worker change, a staggered
response, and an unexplained population-wide switch equally. It also cannot
distinguish a single burst from rapid population switching back and forth.

Legitimate responsiveness and anti-herding are in tension. A valid new
directive can appropriately cause workers to move to a new action, yet a
population-wide instantaneous switch still deserves some penalty. Conversely,
an invalid or stale signal must never excuse a burst. Linux remains the real
scheduler: all actions and transitions in this ADR are userspace policy
selection observations, not CFS/EEVDF dispatch, kernel intent, task state,
context-switch, or performance observations.

## 2. Decision

Create append-only orchestra.paper_cpu.metrics/v4. Its first 66 columns are
the strict v3 contract with unchanged meanings. It adds seventeen experimental
burst diagnostics, including S4_burst. S4_burst neither replaces historical S4
nor changes the historical coordination index:

~~~text
Q = (S1 * S2 * S3 * S4)^(1/4)
~~~

### 2.1 Transition matrix and bounded components

Each eligible worker's current selected action is compared with its prior
selected action. Every changed worker increments one cell in the fixed matrix:

~~~text
transition_counts[old_action][new_action], old_action != new_action
~~~

Canonical IDs are RUN=0, SLEEP=1, MIGRATE=2, THROTTLE=3, and YIELD=4. The
dominant transition is the greatest matrix cell; equal counts use the
lexicographically first old/new pair for deterministic diagnostics. If there
are no changes, both dominant-action cells are the -1 sentinel and the
dominant count is zero. -1 is invalid when any worker changed.

Only canonical old/new pairs enter the matrix. A malformed action snapshot is
non-justifying and cannot index the fixed matrix; valid emitted rows preserve
the normal equality between historical changed count and this metric's changed
eligible count.

~~~text
change_fraction = changed_eligible_workers / eligible_workers

dominant_transition_fraction =
    dominant_transition_count / changed_eligible_workers

population_scale =
    0                                           if eligible_workers <= 1
                                                or changed_eligible_workers <= 1
    (changed_eligible_workers - 1) /
        (eligible_workers - 1)                 otherwise
~~~

change_fraction is zero for zero eligible workers. dominant_transition_fraction
is zero with no changed workers. population_scale guarantees that one worker,
including the single eligible-worker case, is never labelled a synchronized
burst.

### 2.2 Directive-transition justification

current_directive_valid is one only if the current directive is accepted and
fresh and the positive configured non-exempt worker population is fully
represented by eligible coherent snapshots. It is zero for a partial sample,
zero expected population, rejected, stale, unauthenticated, or unavailable
current directive, and no current worker is in fallback. previous_directive_valid
is one only if a prior fully accepted fresh directive exists.

directive_transition_valid is one exactly when both flags are one and their
canonical directives differ. A changed worker is justified only when that flag
is one and its new selected action equals the current directive:

~~~text
justified_change_fraction =
    justified_changed_workers / changed_eligible_workers
~~~

This fraction is zero if no worker changed. Rejected, stale, unauthenticated,
unavailable, or partial signals cannot justify a change. They can be measured
as an unjustified current burst but cannot enter accepted history.

### 2.3 Formula

The initial experimental formula is exactly:

~~~text
burst_penalty =
    0.80 * change_fraction * population_scale *
    dominant_transition_fraction *
    (0.20 + 0.80 * (1 - justified_change_fraction))

oscillation_penalty =
    min(0.50, 0.15 * rolling_window_oscillation_count)

S4_burst = clamp(1 - burst_penalty - oscillation_penalty, 0, 1)
~~~

The population scale leaves a single action change at one. The 0.20 floor
means a valid directive reduces but never removes the cost of an instantaneous
population switch. For an all-worker same-transition burst, the base penalty is
0.80 when unexplained and 0.16 when fully justified. These constants are an
explainable exploratory choice, not a formal optimum or universal calibration.

### 2.4 Bounded oscillation detection

large_burst_event is one only when all of the following are true:

~~~text
changed_eligible_workers > 1
change_fraction >= 0.50
dominant_transition_fraction >= 0.75
~~~

It is based on current transition shape, not directive validity. This makes an
invalid burst observable as unjustified rather than immune, while ensuring one
worker is never a large burst.

The implementation has fixed physical capacity for eight accepted-frame
entries, each of which records whether it contains a large burst. A current
large burst considers only prior accepted entries marked large within
accepted-frame sequence distance <= 4.
rolling_window_burst_count includes the current event plus qualifying prior
events and is bounded 0..5.

A prior transition reverses the current one only when:

~~~text
prior.old_action == current.new_action
prior.new_action == current.old_action
~~~

rolling_window_oscillation_count counts those prior accepted reversals and is
bounded 0..4. It is zero unless the current event is large.
repeated_oscillation_event is one exactly when the current event is large and
the oscillation count is positive. A current invalid large burst may be scored
against prior accepted history, but only a current fully accepted directive can
write history. Invalid signals never seed future history.

### 2.5 Expected cases and zero denominators

| Scenario | S4 | S4_burst |
| --- | --- | --- |
| No changes, including zero eligible workers | 1 | 1 |
| One isolated change | decreases by 1/N | 1 before any history penalty |
| Staggered changes | decreases on changed rows | less penalty than an equivalent same-row burst |
| Valid directive transition followed gradually | decreases on changed rows | isolated/staggered one-worker rows receive no concentration penalty; multiworker rows can be credited but not free |
| Valid directive transition followed immediately by all workers | low | less penalty than unexplained, but not immune |
| Unjustified same-transition mass switch | low | substantially lower |
| Immediate/repeated direction reversal | low per switch | lower than the corresponding single burst |

For no changed workers, S4_burst=1, change_fraction,
dominant_transition_fraction, justified_change_fraction, and population_scale
are zero, dominant IDs are -1/-1, dominant count is zero, and all
oscillation/large-event diagnostics are zero. This also holds for zero eligible
workers. Required invariants are:

~~~text
justified_changed_workers <= changed_eligible_workers <= eligible_workers
dominant_transition_count <= changed_eligible_workers
all normalized metrics are finite and in [0, 1]
oscillation_penalty is finite and in [0, 0.50]
~~~

### 2.6 Complexity

One worker pass plus a five-by-five matrix scan yields O(N + A^2) time per
observation, where A=5, and O(A^2 + 8) fixed auxiliary storage. There is no
dynamic allocation, population rescanning, unbounded loop, or wait in the
metric path.

## 3. Alternatives Considered

### Replace historical S4 or add S4_burst to Q

Rejected. Either change would alter historical v2/v3 evidence and the
specified four-factor Q definition. A new experimental coordination index is
not introduced here.

### Treat every change equally

Retained as historical S4, but insufficient as the only diagnostic because it
cannot identify a concentrated herd.

### Accept any directive as justification

Rejected. It would weaken freshness and integrity boundaries. Affinity success,
a selected action, or a signal frame also cannot prove kernel scheduling
behavior.

### Use unbounded history

Rejected. It conflicts with bounded userspace measurement requirements.

## 4. Evidence, safety, and performance

Deterministic unit tests cover no change, isolated/minority/mixed changes,
staggered and immediate directive responses, unexplained mass switches,
reversals, repeated alternation, rejected/stale frames, zero/all-exempt
populations, fixed-history wraparound, and randomized invariants. The strict
v4 validator rejects impossible counts, invalid action IDs, fraction ranges,
no-change inconsistencies, and invalid justification flags.

The v4 manifest validates the bounded data pipeline, row/header count,
provenance, and invocation-level summaries only. Rows are not independent
experimental repetitions. If host traces lack a burst, labelled synthetic tests
supply semantic coverage; no natural workload observation is fabricated.

Existing authentication, freshness, fallback, learning, consensus, and
controller gates are unchanged. Rejected/stale frames remain telemetry-only:
they cannot cause adaptive learning, consensus/controller update, justification,
or history admission. The metric introduces only bounded userspace arithmetic;
it is not a kernel hook, process-group coordinator, privilege requirement, or
proved scheduler-hot-path budget.

## 5. Compatibility and status

v2 and v3 artifacts remain readable and untouched. v4 has exactly 83 ordered
columns: the first 66 preserve v3 semantics and the final 17 are new burst
diagnostics. A mislabeled, truncated, reordered, or cross-version row is
invalid. Statistical summaries must not silently pool schemas; rerun under one
explicit schema and summarize by invocation.

This ADR supplements ADR 0001's historical S1--S4/Q contract, ADR 0003's
state-conditioned S3, and ADR 0004's effective-action telemetry. It provides
neither kernel scheduler integration, hard-real-time guarantees, distributed
coordination, formal metric optimality, nor causal scheduler-performance
evidence. Formula, thresholds, validity rule, history window, action sentinel,
column order, or Q treatment changes require a new ADR and schema review.
