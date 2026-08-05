# Paper CPU metrics v4

## Status and claim boundary

orchestra.paper_cpu.metrics/v4 is an 83-column, append-only CSV contract for
the canonical ORCHESTRA paper CPU userspace prototype. It is a
userspace-validated telemetry contract with an experimental burst-sensitive
temporal-stability diagnostic. Linux remains the scheduler. No v4 field proves
kernel dispatch intent, kernel scheduler compliance, hard-real-time behavior,
durable CPU placement, CPU-capacity reduction, scheduler performance, or a
causal scheduling benefit.

The first 66 columns are byte-for-byte ordered and semantically unchanged from
metrics v3. Their complete definitions, including effective-action limitations,
are in [the v3 documentation](paper_cpu_metrics_v3.md). The final 17 fields are
new in v4. v2, v3, and v4 observations must never be silently pooled in one
statistical analysis.

Historical S4 remains:

~~~text
S4 = 1 - changed_eligible_workers / eligible_workers
~~~

with value 1 for zero eligible workers. Historical Q remains:

~~~text
Q = (S1 * S2 * S3 * S4)^(1/4)
~~~

S4_burst is not included in Q.

## Header and version detection

A v4 row requires the exact 83-column header in
[paper_cpu_metrics_v4.json](../../experiments/schemas/paper_cpu_metrics_v4.json)
and metrics_schema=orchestra.paper_cpu.metrics/v4 on every row. The validator
detects v2, v3, and v4 by their exact header and, for v3/v4, the explicit
identifier. A truncated, reordered, cross-version-mislabeled, or non-finite
row is invalid.

The v4 append is, in exact order:

~~~text
S4_burst,
change_fraction,
dominant_transition_fraction,
justified_change_fraction,
oscillation_penalty,
dominant_old_action,
dominant_new_action,
changed_eligible_workers,
justified_changed_workers,
dominant_transition_count,
rolling_window_burst_count,
rolling_window_oscillation_count,
current_directive_valid,
previous_directive_valid,
directive_transition_valid,
large_burst_event,
repeated_oscillation_event
~~~

## Formula and transition semantics

The metric compares each eligible worker's current selected action with its
prior selected action and increments one fixed transition_counts[5][5] cell for
each changed worker. Action IDs are RUN=0, SLEEP=1, MIGRATE=2, THROTTLE=3, and
YIELD=4. The largest cell is dominant. Ties select the lexicographically first
old/new canonical action pair. Diagonal cells do not count as a change. Only
canonical old/new pairs enter the matrix; malformed snapshots are non-justifying
and cannot index fixed storage.

~~~text
change_fraction = changed_eligible_workers / eligible_workers

dominant_transition_fraction =
    dominant_transition_count / changed_eligible_workers

population_scale =
    0                                           if eligible_workers <= 1
                                                or changed_eligible_workers <= 1
    (changed_eligible_workers - 1) /
        (eligible_workers - 1)                 otherwise

justified_change_fraction =
    justified_changed_workers / changed_eligible_workers

burst_penalty =
    0.80 * change_fraction * population_scale *
    dominant_transition_fraction *
    (0.20 + 0.80 * (1 - justified_change_fraction))

oscillation_penalty =
    min(0.50, 0.15 * rolling_window_oscillation_count)

S4_burst = clamp(1 - burst_penalty - oscillation_penalty, 0, 1)
~~~

S4_burst is experimental. It is designed to keep isolated or staggered action
changes high while reducing score for large same-transition population switches
and repeated reversals. The formula has no formal optimality claim.

### Directive justification

current_directive_valid is one only when the positive configured non-exempt
population is fully represented by eligible coherent current-frame snapshots,
no current worker is in fallback, and the current directive was accepted and
fresh. previous_directive_valid is one only for a prior fully accepted fresh
directive.

directive_transition_valid is one only when both flags are one and the
canonical directive changed. A changed worker is justified only if
directive_transition_valid is one and its new selected action equals the
current directive. Stale, rejected, unauthenticated, unavailable, or partial
frames have no justification value. They can still show an unjustified burst,
but they do not enter accepted burst history or alter existing safety/learning
behavior.

### Oscillation history

large_burst_event is one only when more than one worker changed,
change_fraction is at least 0.50, and dominant_transition_fraction is at least
0.75. A current large event compares with a fixed physical history of eight
accepted-frame entries, each recording whether it was a large burst, but only
entries marked large at accepted-frame sequence distance at most four are in
its diagnostic window.

A prior dominant transition reverses the current dominant transition when its
old action equals the current new action and its new action equals the current
old action. rolling_window_burst_count includes the current large event plus
qualifying earlier events and is in 0..5. rolling_window_oscillation_count is
the number of qualifying exact reversals and is in 0..4. Only fully accepted
current directives write history. Thus an invalid current burst may be
penalized against prior accepted history but cannot make a future event look
oscillatory.

## New v4 fields

| Column | Type / unit / range | Missing and zero-denominator rule | Semantic definition | Claim limitation |
| --- | --- | --- | --- | --- |
| S4_burst | number, score, [0,1] | forbidden; 1 when eligible or changed count is zero | Experimental formula above | Userspace selected-action diagnostic, not kernel temporal stability |
| change_fraction | number, fraction, [0,1] | forbidden; 0 when eligible count is zero | Changed eligible workers / eligible workers | Not kernel state-transition fraction |
| dominant_transition_fraction | number, fraction, [0,1] | forbidden; 0 when changed count is zero | Dominant identical old/new count / changed workers | Not a kernel transition concentration |
| justified_change_fraction | number, fraction, [0,1] | forbidden; 0 when changed count is zero | Justified changed workers / changed workers | Only a userspace signal-gate classification |
| oscillation_penalty | number, score penalty, [0,0.50] | forbidden; 0 when current event is not large | min(0.50, 0.15 times rolling oscillation count) | Experimental heuristic, not stability proof |
| dominant_old_action | integer, canonical action ID, -1 or [0,4] | forbidden; -1 only when changed count is zero | Old side of deterministic dominant transition | Selected action, not kernel task state |
| dominant_new_action | integer, canonical action ID, -1 or [0,4] | forbidden; -1 only when changed count is zero | New side of deterministic dominant transition | Selected action, not kernel task state |
| changed_eligible_workers | integer, workers, [0,64] | forbidden; 0 with no eligible/changed workers | Eligible workers whose selected action changed | Not actual dispatch/state changes |
| justified_changed_workers | integer, workers, [0,64] | forbidden; 0 without valid directive transition | Changed workers moving to accepted new directive | Not kernel compliance count |
| dominant_transition_count | integer, workers, [0,64] | forbidden; 0 when changed count is zero | Workers in dominant matrix cell | Not kernel transition count |
| rolling_window_burst_count | integer, events, [0,5] | forbidden; 0 when current event is not large | Current large event plus accepted in-window bursts | Fixed local diagnostic history only |
| rolling_window_oscillation_count | integer, reverse events, [0,4] | forbidden; 0 when current event is not large | Accepted in-window exact reversals | Heuristic, not causal proof |
| current_directive_valid | boolean01, boolean, [0,1] | forbidden; 0 for partial, stale, rejected, unavailable, fallback-bearing, or zero expected population | Current full accepted/fresh directive and coherent population flag | Not kernel directive validity |
| previous_directive_valid | boolean01, boolean, [0,1] | forbidden; 0 when no prior accepted directive | Prior fully accepted/fresh directive available | Does not validate current frame |
| directive_transition_valid | boolean01, boolean, [0,1] | forbidden; 0 unless both valid flags are one and directives differ | Valid accepted directive transition flag | Not a Linux scheduling command |
| large_burst_event | boolean01, boolean, [0,1] | forbidden; 0 unless changed >1 and both thresholds hold | Current transition-shape threshold event | Thresholded experimental diagnostic |
| repeated_oscillation_event | boolean01, boolean, [0,1] | forbidden; 0 unless current large event has an accepted reverse | Reversal-event flag | Bounded heuristic, not system-level proof |

All new fields aggregate at the per-publication level. All values are required:
there is no null or missing-value representation. The JSON schema carries the
authoritative exact unit, range, and claim limitation for every column.

## Reconstructable invariants

~~~text
0 <= justified_changed_workers <= changed_eligible_workers <= eligible_workers
0 <= dominant_transition_count <= changed_eligible_workers
dominant_transition_count == 0 iff changed_eligible_workers == 0
dominant IDs == -1/-1 iff changed_eligible_workers == 0
S4 remains 1 - changed / eligible, with the established zero-eligible rule
S4_burst equals the formula above within the declared CSV tolerance
large_burst_event matches changed > 1 and the two thresholds
repeated_oscillation_event == 1 iff large_burst_event == 1
    and rolling_window_oscillation_count > 0
~~~

All normalized values must be finite and within bounds. A stale/rejected current
directive cannot set directive_transition_valid or increase
justified_changed_workers.

## Complexity and migration

The calculation is O(N + A^2) time for N eligible workers and A=5 canonical
actions, with O(A^2 + 8) fixed auxiliary storage. It uses no dynamic allocation
in the metric path.

To migrate an analysis from v3, keep v3 results as historical evidence and run
the same protocol explicitly under v4. Do not backfill v4 data from v3 rows:
v3 lacks transition-matrix, accepted-directive-history, and burst diagnostics.
Compare invocation-level summaries only; individual CSV rows are repeated
within-invocation observations and are not independent experimental repetitions.

The exploratory v4 manifest is
[paper_cpu_exploratory_v4.json](../../experiments/manifests/paper_cpu_exploratory_v4.json).
It validates schema, pipeline, bounded overhead, and summaries only. It makes
no scheduler-performance claim.
