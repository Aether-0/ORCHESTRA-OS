# ADR 0001: Userspace State, Metric, Reward, and Controller Contract

- Status: Accepted - implemented in the userspace prototype; further validation pending
- Date: 2026-08-03
- Decision class: Specified and userspace-implemented
- Evidence status: Unit- and integration-tested userspace mechanics; not Experimentally validated
- Maturity scope: Single-host userspace prototype only
- Work packages: WP4 Adaptive Process Scheduling, WP5 Coordination Measurement and Feedback Control, and WP6 Instrumentation
- Supersedes: None
- Superseded by: None

## 1. Context

The ORCHESTRA-OS paper reports a controlled, pre-kernel simulation. The maintained `orchestra_paper_cpu_demo/orchestra_paper_cpu.c` is a real-process userspace approximation: it observes a real Linux host and asks processes to sleep, yield, change affinity, throttle themselves, or consume CPU. Linux CFS/EEVDF still performs final dispatch. Neither this ADR nor a passing userspace test establishes a Linux scheduling-class implementation.

The original userspace table (`state-v1`) had five CPU buckets and three thermal buckets. It omitted memory pressure even though memory pressure can change the directive, and its half-open bucket boundaries did not exactly match the directive's strict comparisons. The maintained C now advertises `STATE_SCHEMA_VERSION == 2`, includes CPU, memory, and thermal dimensions, and uses upper-inclusive bucket endpoints that match those comparisons before intentional per-worker jitter is applied.

The paper constrains the rest of this contract through several corrective and negative results:

- local directive reward is `+0.6` for a match and `-0.6` for a mismatch;
- table-state boundaries must follow directive boundaries;
- temporal stability requires an explicit `S4` term;
- the reported aggregate must be a normalized geometric mean;
- a controller must use an actuator with a causal path to the deficient submetric;
- the outer controller must update more slowly than the inner learner;
- the failed innovation-only online adaptive Kalman design must not be reintroduced without resolving identifiability; and
- difference rewards must provide population credit without displacing the local directive signal.

This ADR records the behavior implemented by the current userspace C. Requirements described under "Unimplemented future gates" are limitations, not claims about the current program.

## 2. Decision

### 2.1 Scope and version identifiers

The C signal carries numeric state schema version `2`. The machine-readable CSV contract is maintained separately as `orchestra.paper_cpu.metrics/v2`. The program prints signal- and state-schema numbers, mode, seed, and run configuration to diagnostics; the CSV rows do not carry a state-schema or metric-schema identifier themselves.

The canonical action set remains exactly:

```text
RUN, SLEEP, MIGRATE, THROTTLE, YIELD
```

Signal payload validation requires finite normalized state and confidence values and bounded controller values before a worker accepts the frame. This ADR does not redefine the signal-frame byte contract.

### 2.2 Directive, prediction fallback, and state schema v2

The directive uses this exact precedence:

```text
if thermal > 0.90 or decision_cpu > 0.94: THROTTLE
else if decision_cpu > 0.82 or memory > 0.90: MIGRATE
else if decision_cpu > 0.68: YIELD
else if decision_cpu < 0.20: SLEEP
else: RUN
```

In ORCHESTRA mode, `decision_cpu` is predicted CPU only when confidence is finite and at least `0.50`; otherwise it is observed CPU. Baseline mode always uses observed CPU. The chosen value is clamped to `[0, 1]`.

Each adaptive worker then forms a private perceived CPU value:

```text
perceived_cpu = clamp(decision_cpu + normal_noise * jitter_sigma, 0, 1)
```

The global directive uses unjittered `decision_cpu`; the worker table state uses `perceived_cpu`. The resulting occasional directive/state disagreement is the intentional anti-synchronization tradeoff, not a bucket-boundary mismatch.

State v2 is the Cartesian product of five CPU buckets, two memory buckets, and three thermal buckets. The exact implementation intervals are:

| Dimension | Bucket | Exact interval |
| --- | ---: | --- |
| CPU | C0 | `[0.00, 0.20)` |
| CPU | C1 | `[0.20, 0.68]` |
| CPU | C2 | `(0.68, 0.82]` |
| CPU | C3 | `(0.82, 0.94]` |
| CPU | C4 | `(0.94, 1.00]` |
| Memory | M0 | `[0.00, 0.90]` |
| Memory | M1 | `(0.90, 1.00]` |
| Thermal | T0 | `[0.00, 0.70)` |
| Thermal | T1 | `[0.70, 0.90]` |
| Thermal | T2 | `(0.90, 1.00]` |

The `0.70` thermal split is a retained policy feature boundary; `0.90` is the strict thermal directive boundary. State and Q-table indices are:

```text
state_id = ((cpu_bucket * 2) + memory_bucket) * 3 + thermal_bucket
q_index = state_id * 5 + action_id
```

There are 30 states (`state_id` in `[0, 29]`) and 150 Q values (`q_index` in `[0, 149]`). With C `double` values, the Q array occupies 1,200 bytes per worker, excluding other worker metadata and alignment. State v1 had 75 Q values and occupied 600 bytes.

Workers start with zeroed Q-tables in fresh anonymous shared memory. No policy persistence, in-place v1-to-v2 conversion, or resume path exists. A frame with a state-schema version other than `2` is rejected before use. Because every worker is compiled into the same executable, the current program does not negotiate heterogeneous per-worker schemas.

### 2.3 Local and bounded difference rewards

Reward assignment snapshots alive, non-exempt workers whose per-worker decision seqlock can be read coherently. Fallback workers remain part of this population. The parent invokes reward assignment only when every configured non-exempt worker is present in the metric snapshot and has coherently published acceptance of the current frame sequence. A rejected, lagged, or incomplete frame sample therefore cannot replace a stored reward.

Population utility is the exact, zero-preserving geometric mean of action-dependent components:

```text
G(a_vector) = (S2 * S3 * S4)^(1/3)
```

For worker `i`, the counterfactual replaces that worker's action with fixed baseline action `YIELD` while retaining the population size:

```text
D_raw_i = n * (G(a_vector) - G(a_without_i, YIELD_i))
D_i = clamp(D_raw_i, -0.6, +0.6)
```

The local term is:

```text
L_i = +0.6, if selected_action == directive
L_i = -0.6, otherwise
L_i -= 0.4, if thermal > 0.90 and selected_action == RUN
L_i -= switch_penalty, if selected_action != previous_action
```

The final stored reward is:

```text
R_i = 0.70 * L_i + 0.30 * D_i
```

The thermal penalty cannot penalize the valid directive because `thermal > 0.90` directs `THROTTLE`. With switching penalty bounded to `0.30`, the implemented difference clamp preserves directive dominance even under opposite extreme difference rewards:

```text
minimum correct reward = 0.70 * (0.60 - 0.30) + 0.30 * (-0.60) = 0.03
maximum incorrect reward = 0.70 * (-0.60) + 0.30 * (+0.60) = -0.24
minimum correct advantage = 0.27
```

The final reward is not globally clamped: thermal and switching penalties can make an incorrect action's reward lower than `-0.60`. The C stores the final reward together with an atomic frame-sequence stamp. A worker consumes it only when the stamp matches the action transition being updated, then clears the stamp; an absent, stale, or already consumed reward does not update the Q value. The program does not emit local, raw difference, clamped difference, final reward, or reward-sequence telemetry.

Exact counterfactual evaluation is approximately quadratic in eligible-worker count and is performed in the userspace parent, not a kernel scheduler hot path.

### 2.4 Coordination metrics

Each worker exposes action, previous action, alive/exempt/fallback flags, and accepted sequence through a per-worker decision seqlock. `compute_metrics` omits a worker if that coherent snapshot cannot be obtained, if it is not alive, or if it is real-time exempt. It does not create one globally simultaneous snapshot across all workers.

The metric structure also counts workers whose accepted sequence exactly equals
the frame being scored. That current-acceptance count is internal and is not a
CSV column. Metrics remain observable when acceptance is incomplete so S1 can
show lost reach, but reward assignment and outer-controller action are gated on
all configured non-exempt workers being present and current.

Let `N` be the resulting eligible count. Fallback workers are included in the action metrics and are separately counted.

The implemented signal score is:

```text
age_seconds = max(0, now_monotonic - frame.monotonic_time)
freshness = exp(-2 * max(0, age_seconds - interval_seconds))
accuracy = exp(-4 * forecast_error)
signal_reach = mean(exp(-0.7 * (frame.sequence - worker.accepted_sequence)))
S1 = clamp(freshness * accuracy * frame.confidence * signal_reach, 0, 1)
```

The sequence gap is floored at zero. When `N == 0`, `signal_reach` is `1`.

The behavioral components are:

```text
S2 = matching_selected_actions / N

H = -sum(p_a * ln(p_a)) for p_a > 0
S3 = 1 - H / ln(5)

S4 = 1 - changed_actions / N
```

For entropy, `p_a` is the fraction selecting canonical action `a`. Normalized entropy is defined as zero when `N <= 1`, making `S3 = 1`. When `N == 0`, the C reports `S2 = S3 = S4 = 1`; it emits `eligible_workers = 0` but no separate sample-validity flag. `S4` uses every eligible worker in the denominator, including a worker's first observed action transition; there is no separate `N_temporal` cohort.

S3 is whole-population action entropy, not a state-conditioned comparison among similarly situated workers. Unanimous incorrect behavior can therefore have `S3 = 1`; exact `S2 = 0` makes aggregate Q zero.

The reported index is the exact zero-preserving four-factor geometric mean:

```text
Q = 0, if any clamped factor is non-positive
Q = exp((ln(S1) + ln(S2) + ln(S3) + ln(S4)) / 4), otherwise
```

The helper clamps every factor to `[0, 1]`; its clamp maps non-finite values to zero. It does not insert an epsilon floor. Stable unanimous wrong action and a unanimous mass switch therefore both produce exact `Q = 0` through `S2 = 0` and `S4 = 0`, respectively.

### 2.5 Controller cadence, inputs, and actuators

The controller runs only in ORCHESTRA mode, only when `tick % 20 == 0`, and only for a complete current-frame acceptance sample. A scheduled update is skipped rather than allowing a rejected or incomplete frame to change actuators or Q-table consensus. It uses the instantaneous `S3` and `S4` values computed at that tick, not a rolling 20-tick mean.

The controller step is one-based in the maintained C. `controller_step` starts at zero, is incremented before the first update at tick 20, and is then passed to:

```text
beta_step = 0.02 / sqrt(1 + controller_step)
```

Thus the first update reports step `1` and beta `0.02 / sqrt(2)`. At non-update rows, the most recent step remains visible while beta and reason remain zero/`NONE`.

The threshold is `0.82`, with strict less-than comparisons. The causal mapping and rates are:

| Instantaneous condition | Actuator change | Runtime bounds |
| --- | --- | --- |
| `S4 < 0.82` | jitter `+= 0.20 * beta`; otherwise `-= 0.05 * beta` | `[jitter_min, 0.20]` |
| `S3 < 0.82` or `S4 < 0.82` | switching penalty `+= 0.15 * beta`; otherwise `-= 0.04 * beta` | `[0.00, 0.30]` |
| `S3 < 0.82` | consensus blend `+= 0.10 * beta`; otherwise `-= 0.03 * beta` | `[0.00, 0.15]` |

Calibration computes `1.5 * sigma_observation` and caps it at `0.20`. `controller_update` defensively clamps the supplied floor into `[0, 0.20]`; a floor greater than `0.20` therefore yields `jitter_min = 0.20` rather than rejecting the configuration. Jitter is always clamped between that effective floor and `0.20`.

For each actuator, the controller first computes a raw requested value. Its saturation flag is true only if that raw value lies below the lower bound or above the upper bound; an exactly-on-bound request is not flagged. It then clamps the applied next value.

The metrics and rewards for tick `t` use the actuator values published at tick `t`. On a controller tick, the new jitter and switching values are retained for publication at tick `t+1`. Consensus is different: the program immediately attempts consensus at tick `t` using the newly computed blend. CSV output distinguishes applied actuator values from `next_*` values.

The controller does not act on `S1`, `S2`, or aggregate Q and does not retune predictor gain, noise covariance, prediction horizon, or sampling interval. Predictor gain is selected once during the pre-run calibration trace. Confidence below `0.50`, rather than an `S1` controller branch, switches the ORCHESTRA directive input to observed CPU.

### 2.6 Consensus behavior

The operational controller path passes a blend in `[0, 0.15]`. The consensus helper itself does not clamp an arbitrary direct caller's blend.

When blend is non-positive, consensus returns false without taking the lock. Otherwise it:

1. sets the shared consensus lock;
2. waits up to 200 iterations of approximately 1 ms for all `q_update_active` flags to clear;
3. returns false without changing tables if a Q-table access remains active after that wait;
4. computes each Q cell's arithmetic mean across non-exempt workers;
5. applies `(1 - blend) * local + blend * mean` to every non-exempt table; and
6. releases the lock and returns true.

Despite its historical name, `q_update_active` now covers both Q-value updates
and Q-table reads used for action selection. A worker publishes that flag and
then rechecks the consensus lock before touching its table; if consensus won
the race, the worker clears the flag and retries. The sequentially consistent
two-flag handshake ensures the parent does not blend a table while its owner is
reading or writing it.

The convex runtime blend preserves the population mean of each Q cell. Consensus can execute on a controller tick even when instantaneous `S3` is healthy, because an existing positive blend decays gradually rather than becoming zero immediately. `consensus_applied` reports only whether the blend completed; it does not distinguish zero blend, no eligible participants, or timeout.

Consensus excludes workers marked real-time exempt but does not separately test their alive state. Schema compatibility is implicit because all workers share one executable and one compile-time Q-table shape; there is no per-worker schema negotiation or mismatch event.

### 2.7 Emitted telemetry

The version-2 CSV currently emits:

- tick and mode;
- observed, predicted, and decision CPU;
- whether prediction was used, confidence, forecast error, and frame age;
- memory, thermal proxy, and directive;
- selected-action counts, eligible-worker count, and fallback-worker count;
- `S1`, `S2`, `S3`, `S4`, and Q;
- applied jitter, switching penalty, and consensus blend;
- `next_jitter_sigma`, `next_switch_penalty`, and `next_consensus_blend`;
- controller-updated flag, one-based step, reason (`NONE`, `S3`, `S4`, or `S3+S4`), and beta;
- one-tick jitter, switching, and consensus saturation flags;
- `consensus_applied`;
- cumulative rejected-frame count; and
- cumulative missed-deadline count.

The current CSV does not emit per-worker state or accepted sequence, the internal current-acceptance count or an explicit controller-skip reason, raw/requested actuator values, bound values, saturation streaks, consensus participant count or timeout reason, reward components, Q-table values, fallback entry/exit reasons, action syscall outcomes, or final Linux dispatch outcomes. The startup diagnostic prints seed and signal/state schema numbers; those identifiers are not repeated in each CSV row.

### 2.8 Unimplemented future gates and limitations

The following are research requirements or desirable gates that the current C does not implement:

- a rolling-window controller input matching the paper's rolling-average description;
- consecutive-saturation counters, sustained-saturation alerts, rollback, and controller disable/re-entry state;
- an explicit non-finite controller-input rejection path with a last-known-good controller vector;
- per-worker state/action schema advertisement and selective consensus disablement for heterogeneous schemas;
- a metric-validity flag for zero eligible workers;
- state-conditioned S3 for similarly situated processes;
- one globally coherent population snapshot or explicit incomplete-snapshot telemetry;
- reward-component and consensus-participant diagnostics;
- a conventional-scheduler fallback after signal expiry - the current worker records fallback and selects userspace `THROTTLE`;
- verified action outcomes, migration failures, affinity results, and Linux dispatch outcomes;
- independently held-out predictor calibration, parameter artifact versioning, and recalibration triggers;
- a bounded kernel-hot-path approximation for difference rewards;
- kernel, NUMA, node, or cluster controller semantics; and
- repeated-workload statistical evidence for performance, stability, fairness, latency, energy, or generalization claims.

These limitations must not be described as completed functionality merely because the state, metric, reward, and controller unit tests pass.

### 2.9 Claims

The maintained C implements the userspace mechanics described above and exercises real processes. The supported claim is limited to a userspace prototype whose selected paths are covered by unit and short integration tests. It does not establish kernel correctness, hard-real-time guarantees, experimental performance superiority, distributed coordination, production security, or deployment readiness.

## 3. Alternatives Considered

### Retain state v1

Rejected because memory pressure changes the directive but was absent from the table state, and strict boundary values could share a bucket with observations requiring another action.

### Add singleton buckets for threshold values

Rejected because upper-inclusive and lower-exclusive intervals express the strict comparisons exactly without increasing the state count beyond 30.

### Use a function approximator instead of a table

Deferred. It removes this particular discretization constraint but introduces different verification, reproducibility, memory, and safety questions. The interpretable table remains appropriate for this userspace research stage.

### Preserve a raw or epsilon-floored product

Rejected. A raw product changes scale as dimensions are added, and an epsilon floor reports nonzero coordination when a required component is exactly zero.

### Drive the controller from aggregate Q or retune predictor gain online

Rejected. Aggregate Q does not identify a causal actuator, and the paper's innovation-only online adaptive Kalman attempt could not identify process and observation noise and performed substantially worse than the calibrated estimator.

### Use rolling controller inputs

Deferred rather than implemented. A rolling input would more closely match the paper's narrative and could reduce single-snapshot sensitivity, but its window, latency, and stability effects require a versioned experiment.

### Leave the difference reward unbounded

Rejected because population scaling could allow the population term to dominate the validated local directive reward.

### Update the outer controller every tick

Rejected because it would collapse the intended separation between the inner learning process and outer controller.

## 4. Scientific and Engineering Evidence

The paper reports that directive-matched reward improved compliance, directive-aligned buckets removed a structural state ceiling, `S4` exposed synchronized mass switching, geometric-mean aggregation restored cross-version scale, and the three actuator classes target `S3` and `S4` deficits more directly than predictor retuning.

The maintained source implements state schema version 2, zero-preserving geometric means, a `[-0.60, +0.60]` difference clamp, one-based decaying controller steps, actuator bounds and saturation flags, coherent per-worker decision snapshots, and bounded consensus timeout behavior.

The unit suite characterizes strict directive boundaries, all 30 state buckets over boundary-adjacent samples, epsilon decay, zero-preserving metric cases, three-worker difference-reward cases, controller mapping/rates/bounds, predictor helpers, and consensus blending/timeout. The integration suite performs short baseline, adaptive, tamper, cadence, CSV-contract, and teardown checks. These tests support implementation correctness for exercised cases; they are not repeated benchmark evidence or statistical experimental validation.

The exact thresholds, rates, and bounds remain experiment-specific implementation choices. They are not universal scheduler constants.

## 5. Safety and Security Implications

- Accepted frames carry state schema version 2 and bounded normalized inputs before workers index their tables.
- The difference clamp and switching bound preserve the directive action's reward ordering under the implemented reward terms.
- Controller updates have decaying steps, fixed cadence, bounds, and one-update saturation flags.
- Consensus abandons the blend rather than modifying Q-tables after its bounded wait expires.
- Invalid or expired signal service eventually records fallback and selects userspace `THROTTLE`; this is not the full conventional-scheduler fallback required by the research program.
- Real-time-designated workers bypass adaptive learning, but an unprivileged failure to enter `SCHED_FIFO` means the prototype cannot claim hard-real-time behavior.
- Selected action and userspace approximation are not proof of final kernel dispatch or successful migration.
- This ADR makes no production-security or kernel-safety claim.

## 6. Performance Implications

State v2 adds 600 bytes of Q values per worker, doubling Q-table storage from 600 to 1,200 bytes. Q lookup and update remain constant time.

Difference-reward computation is approximately O(N^2) in eligible workers. Metric collection performs bounded per-worker snapshot retries. Consensus is O(N * 150) per completed blend and may wait up to approximately 200 ms for active Q-table accesses, which can exceed short signal intervals; the program records aggregate missed publication deadlines but not consensus wait duration.

CSV telemetry adds formatted output each tick. The present unit and integration tests do not quantify disabled/enabled instrumentation overhead, tail latency, fairness, migration cost, cache effects, or energy. No performance conclusion follows from this ADR.

## 7. Compatibility and Migration Plan

State v2 is intentionally incompatible with v1. The current prototype has no saved-policy format, so migration is a restart with zeroed 150-entry Q-tables. Signal frames whose state-schema value is not `2` are rejected.

All workers in one run must use the same executable and table shape. Mixed v1/v2 consensus is unsupported rather than dynamically negotiated. The CSV schema is version 2 in the external schema and experiment manifest; comparisons with older sample CSV files require explicit schema qualification.

Rollback to v1 requires a clean restart and must not reinterpret a v2 table. Any future persisted-policy format, heterogeneous worker schema, or in-place migration requires a superseding ADR with provenance, validation, reset, and compatibility rules.

## 8. Status and Superseding ADRs

This decision is accepted and implemented in the maintained userspace prototype. Unit and short integration tests cover the mechanics listed in Section 4. The evidence supports only those exercised userspace paths; experimental validation, kernel prototyping, distributed implementation, and deployment readiness remain unachieved.

No ADR is superseded. A future ADR must supersede this one if it changes directive thresholds, state dimensions, reward weights or bounds, S1-S4 definitions, aggregation, controller inputs or mapping, cadence, step indexing, actuator bounds, consensus behavior, telemetry semantics, or policy migration.
