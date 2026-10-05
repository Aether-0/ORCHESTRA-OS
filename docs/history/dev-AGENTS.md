# AGENTS.md — ORCHESTRA-OS Complete Research Program

## 1. Purpose

This repository supports the complete **ORCHESTRA-OS research program**, not merely a simulator or a real-CPU userspace demonstration.

ORCHESTRA-OS is a predictive, cryptographically protected, hierarchical, signal-coordinated scheduling architecture intended to progress through:

1. simulation-driven architectural discovery;
2. real-hardware userspace validation;
3. Linux kernel integration;
4. secure signal-bus implementation;
5. predictive scheduling;
6. adaptive per-process scheduling;
7. coordination measurement and feedback control;
8. instrumentation and experimental validation;
9. multi-core, NUMA, node, and cluster scaling;
10. security, reliability, optimization, and deployment-readiness assessment.

Codex must treat this repository as a **scientific systems-research project**. Every change must improve at least one of the following without weakening the others:

- architectural fidelity;
- kernel correctness;
- safety and recoverability;
- experimental validity;
- reproducibility;
- observability;
- security;
- scalability;
- maintainability;
- honesty of claims.

Do not optimize for impressive demos at the cost of scientific rigor.

---

## 2. Authoritative sources and precedence

Use the following source-of-truth order when requirements conflict:

1. The latest approved ORCHESTRA-OS research specification or architecture decision record.
2. The ORCHESTRA-OS research paper.
3. The approved work-package roadmap covering Work Packages 1–10.
4. This `AGENTS.md`.
5. Repository-level design documents and interface specifications.
6. Tests and experiment manifests.
7. Current implementation.
8. General operating-system knowledge and engineering inference.

The paper reports a **pre-kernel simulation study**. The work-package document describes a **future implementation and validation program**. Planned work is not evidence of completed functionality.

When a source is ambiguous:

- preserve the ambiguity;
- record the engineering interpretation in an ADR;
- distinguish source-derived requirements from implementation choices;
- do not silently invent a research claim.

When a newer approved design intentionally departs from the paper, document:

- the original paper behavior;
- the new behavior;
- the reason for the change;
- the evidence supporting it;
- the compatibility and measurement consequences.

---

## 3. Scope boundary

This repository implements and evaluates the research architecture described by the ORCHESTRA-OS paper and approved work packages.

Do not introduce unrelated scheduling architectures into the core research path. In particular, do not add an external process-group coordinator, group runnable budgets, group-level error handling, or another user-proposed scheduling layer unless it is explicitly approved as a separate experiment with its own hypothesis, branch, and documentation.

The canonical ORCHESTRA hierarchy is:

```text
core-local tier
    ↓
node / socket / NUMA tier
    ↓
cluster tier
```

This hierarchy concerns signal aggregation, dissemination, coordination measurement, and control across system levels. It is not an unspecified process-group abstraction.

Exploratory ideas are allowed only when isolated under `research/experiments/` and clearly labeled as non-canonical.

---

## 4. Research status and claim classes

Every feature, document, result, and public statement must be classified as one of:

- **Specified** — described by an approved source.
- **Simulated** — implemented only in a controlled simulator.
- **Userspace-validated** — exercised with real processes and hardware measurements but without replacing the Linux scheduler.
- **Kernel-prototyped** — integrated into a test kernel or an extensible scheduling framework.
- **Experimentally validated** — evaluated using a documented protocol with repeated runs and statistical analysis.
- **Deployment-ready** — passed the approved functionality, performance, security, reliability, maintainability, and operational-readiness gates.
- **Exploratory** — a hypothesis or unvalidated extension.

Never use a stronger class than the evidence supports.

Examples:

- A userspace process calling `sched_yield()` is not a kernel scheduler implementation.
- Detecting injected HMAC failures in simulation is not proof of production security.
- A short run on one machine is not a general performance result.
- A planned core/node/cluster design is not a completed distributed scheduler.

---

## 5. Canonical architecture

Preserve the following closed-loop structure:

```text
hardware and kernel observations
        ↓
predictive extrapolation layer
        ↓
versioned Global Signal Vector
        ↓
cryptographic integrity and freshness protection
        ↓
hierarchical read-only signal dissemination
        ↓
per-process Adaptive Response Function
        ↓
RUN / SLEEP / MIGRATE / THROTTLE / YIELD
        ↓
Hybrid Safety Layer and Linux dispatch
        ↓
S1 / S2 / S3 / S4 coordination measurement
        ↓
multi-actuator, slower-timescale feedback control
        └───────────────────────────────────────↺
```

### 5.1 Architectural components

The complete research architecture consists of:

1. **System-state acquisition**
   - CPU utilization;
   - memory pressure;
   - thermal state;
   - cache behavior;
   - I/O activity;
   - network utilization;
   - run-queue and scheduler-domain statistics;
   - relevant historical execution information.

2. **Predictive Extrapolation Layer**
   - short-horizon forecasting;
   - calibrated model parameters;
   - prediction confidence;
   - stale-prediction rejection;
   - observed-state fallback.

3. **Signal Bus**
   - structured, fixed-version frames;
   - current and predicted state;
   - directive and confidence metadata;
   - timestamp and sequence information;
   - core, node, and cluster tiers;
   - low-latency, read-only access.

4. **Signal Integrity Module**
   - authentication;
   - integrity checking;
   - freshness checking;
   - replay protection;
   - sequence validation;
   - key lifecycle and rotation;
   - fail-closed behavior.

5. **Adaptive Response Function**
   - per-eligible-process policy;
   - compact state representation;
   - bounded action set;
   - learning or adaptation;
   - local and population-level reward signals.

6. **Hybrid Safety Layer**
   - deterministic bypass for hard real-time tasks;
   - eligibility and admission rules;
   - safe fallback to conventional Linux scheduling;
   - bounded adaptive authority.

7. **Coordination Measurement Framework**
   - signal fidelity;
   - directive compliance;
   - action coherence;
   - temporal stability;
   - per-process, per-core, per-node, and system-level views.

8. **Closed-Loop Feedback Controller**
   - submetric-aware diagnosis;
   - matched actuators;
   - stable update rates;
   - bounded parameters;
   - convergence and saturation monitoring.

9. **Instrumentation and Diagnostics**
   - event tracing;
   - prediction monitoring;
   - action and policy tracing;
   - coordination analytics;
   - controller analytics;
   - performance, security, and reliability telemetry.

10. **Multi-level coordination**
    - multi-core and socket coordination;
    - NUMA-aware placement;
    - inter-node signal exchange;
    - distributed synchronization;
    - hierarchical feedback control;
    - graceful degradation.

---

## 6. Canonical action set

For an eligible process, the research action set is exactly:

```text
RUN
SLEEP
MIGRATE
THROTTLE
YIELD
```

Do not add `WAIT` as a sixth canonical action. Waiting must be represented through sleeping, yielding, throttling, or conventional scheduler state.

Each action must have a precise implementation contract at each maturity level:

- simulator semantics;
- userspace real-CPU semantics;
- kernel scheduler semantics;
- distributed/cluster semantics where applicable.

Do not assume userspace approximations and kernel semantics are equivalent.

---

## 7. Coordination metric invariants

The corrected Coordination Index is:

```text
Q(t) = (S1(t) × S2(t) × S3(t) × S4(t))^(1/4)
```

Each component and the aggregate must be finite and bounded in `[0, 1]`.

### 7.1 S1 — signal fidelity and freshness

`S1` must reflect at least:

- frame age;
- successful integrity verification;
- prediction error after the observed value becomes available;
- expiry or staleness.

A rejected, stale, or unverifiable frame must not receive full fidelity.

### 7.2 S2 — directive compliance

`S2` is the fraction of eligible, non-exempt processes whose selected action matches the valid directive under the experiment's declared compliance rule.

The compliance rule must be versioned and must not change silently between runs.

### 7.3 S3 — action coherence

`S3` must measure whether similarly situated processes behave coherently without rewarding meaningless uniformity.

The implementation must state whether coherence uses:

- normalized variance;
- normalized entropy;
- policy distance;
- another approved definition.

Do not compare values produced by materially different definitions without conversion or explicit qualification.

### 7.4 S4 — temporal stability

`S4` must penalize synchronized mass action changes. A population that flips actions in lockstep must not score as perfectly coordinated merely because every process agrees at a single tick.

Tests must include deliberate thundering-herd traces.

### 7.5 Aggregation

Do not revert to the raw product `S1 × S2 × S3 × S4` as the reported index. The geometric mean preserves AND-like collapse while keeping scores comparable when metric dimensionality changes.

If a new component is proposed:

1. justify why it is not already represented;
2. define its range and failure meaning;
3. evaluate correlation with existing components;
4. update the root exponent;
5. provide backward-comparability analysis;
6. update tests and result schemas.

---

## 8. Learning and adaptation invariants

### 8.1 Reward consistency

The validated local directive reward is:

```text
+0.6 when selected action matches the directive
-0.6 otherwise
```

Additional safety, switching, energy, or fairness terms must not make the optimal local action contradict the directive without an explicit policy change.

Whenever the directive function changes, update together:

- reward logic;
- state boundaries;
- compliance scoring;
- tests;
- documentation;
- experiment version.

### 8.2 State representation

For tabular policies, state buckets must align with directive thresholds. One state must not contain observations requiring different correct directives unless the ambiguity is intentional and measured.

State changes require:

- a versioned state schema;
- migration or reset rules for saved policies;
- coverage tests at every threshold boundary;
- an analysis of state-space growth and per-task memory cost.

### 8.3 Exploration

The paper's validated simulation anneals epsilon from `0.30` toward `0.02`, using an exponential decay near `0.998` per tick in the reported setup.

Do not keep a high fixed exploration rate and then interpret capped compliance as policy failure.

Kernel implementations must assess whether online exploration is safe. Exploration authority must be bounded, and unsafe actions must be blocked by the Hybrid Safety Layer.

### 8.4 Difference rewards

The validated simulation blends a local directive reward with a difference reward using approximately:

```text
w = 0.30
```

The difference reward estimates each agent's marginal contribution to population utility. Preserve the local reward as the dominant signal unless a new controlled experiment supports a change.

Do not use an expensive exact counterfactual computation in a scheduler hot path without a cost analysis and bounded approximation.

### 8.5 Consensus

Q-table or policy consensus is an actuator for policy divergence, not a substitute for all local learning.

Consensus must be:

- bounded;
- infrequent relative to local decisions;
- measurable;
- disabled for incompatible state/action schemas;
- evaluated for homogenization and correlated-failure risks.

---

## 9. Predictor invariants

### 9.1 Negative result must be preserved

The research found that an online-adaptive Kalman approach based on insufficient innovation statistics performed substantially worse because process and observation noise were not jointly identifiable in that setup.

Do not delete or hide this result. Do not reintroduce the same estimator under a new name without addressing identifiability.

### 9.2 Calibration

The validated direction is an offline-calibrated lightweight estimator using a held-out trace.

A compliant calibration workflow must:

1. separate calibration and evaluation data;
2. record workload and hardware metadata;
3. version model parameters;
4. prevent evaluation look-ahead;
5. report forecast error and latency;
6. define recalibration triggers;
7. support fallback when confidence is inadequate.

### 9.3 Prediction confidence

Every production-oriented prediction must include a confidence or validity measure. Low-confidence forecasts must degrade gracefully toward observed-state scheduling, not produce unbounded adaptive behavior.

### 9.4 Predictor budget

Prediction must fit within the declared scheduling-time budget. Measure:

- mean latency;
- tail latency;
- CPU cost;
- memory cost;
- cache effects;
- missed update deadlines.

A more accurate predictor is not automatically better if it violates the scheduler budget.

---

## 10. Anti-synchronization invariants

Per-agent perceptual jitter is a symmetry-breaking mechanism derived from the observed noise scale, not an arbitrary random disturbance.

The reported default relation is:

```text
jitter_floor = c × sigma_observation
c ≈ 1.5
```

A robust estimator of observation noise should be used where load spikes create outliers.

Any jitter change must evaluate the tradeoff between:

- compliance `S2`;
- temporal stability `S4`;
- migration bursts;
- latency;
- fairness;
- run-to-run variance.

Never maximize `S4` alone by making processes unresponsive to legitimate signal changes.

---

## 11. Controller invariants

The original single-actuator PID design was inadequate because it adjusted a predictor parameter when the deficit was in population compliance and coherence.

The controller must diagnose the deficient submetric and select a causally relevant actuator.

Canonical actuator mapping:

- perceptual jitter → synchronized switching / `S4`;
- switching penalty → excessive switching / `S3` and `S4`;
- bounded policy consensus → policy divergence / `S3`;
- prediction horizon or gain → `S1` only when forecast quality is actually deficient;
- sampling interval → signal freshness and overhead, subject to stability limits.

### 11.1 Two-timescale requirement

The controller must evolve more slowly than the inner learning process.

The reported simulation updates the controller every 20 ticks and uses a decaying controller step approximately proportional to:

```text
beta_k = beta_0 / sqrt(1 + k)
```

Do not mutate rewards or policy parameters every tick at constant magnitude.

### 11.2 Safety limits

Every actuator requires:

- minimum and maximum bounds;
- rate limits;
- saturation detection;
- rollback or fallback behavior;
- telemetry;
- tests for oscillation and runaway adaptation.

---

## 12. Signal-bus and security invariants

### 12.1 Signal frame

Use an explicitly versioned frame. At minimum, define:

- magic and schema version;
- tier and source identity;
- sequence number;
- monotonic timestamp;
- expiry or maximum age;
- observed state;
- predicted state;
- prediction horizon;
- confidence;
- directive;
- coordination metadata where appropriate;
- key epoch;
- authentication tag.

Do not authenticate native struct bytes as a portable protocol. Use canonical serialization with defined field sizes, byte order, padding rules, and floating-point or fixed-point encoding.

### 12.2 Verification order

A consumer must:

1. obtain a coherent snapshot;
2. validate schema and bounds;
3. validate source/tier identity;
4. validate sequence and freshness;
5. derive or obtain the correct key epoch;
6. verify the authentication tag in constant time;
7. accept the frame only after all checks pass.

Invalid frames must not influence a new adaptive decision.

### 12.3 Key management

Key distribution was not solved by the simulation. Treat it as a first-class research and engineering problem.

Document:

- root of trust;
- key generation;
- provisioning;
- per-tier derivation;
- rotation;
- overlap windows;
- revocation;
- node join/leave behavior;
- compromise recovery;
- auditability.

Never commit production keys, fixed test secrets, or private credentials.

### 12.4 Failure behavior

Support:

- recent last-known-good frames within a bounded safety window;
- observed-state fallback when prediction fails;
- conventional scheduler fallback when signal coordination is unsafe;
- local scheduling continuity when a higher hierarchy level fails;
- explicit recovery and re-entry conditions.

Fail closed for integrity, but fail operationally safe for scheduling.

---

## 13. Hybrid Safety Layer

Hard real-time tasks using conventional deterministic classes such as `SCHED_FIFO` or `SCHED_RR` must bypass the adaptive signal path.

The kernel implementation must define:

- eligibility flags;
- admission and removal rules;
- precedence in the scheduling hierarchy;
- interaction with deadline and real-time classes;
- starvation prevention;
- transition rules;
- fallback behavior;
- observability.

Do not claim hard-real-time guarantees from userspace emulation or from an unprivileged test that failed to enter the intended real-time class.

Adaptive policy must never override safety-critical deterministic scheduling without an approved safety case.

---

## 14. Ten research design principles

All implementation and review decisions should respect these principles distilled from the study:

1. **Coordination metrics must encode temporal stability**, not only instantaneous agreement.
2. **Use a normalized aggregation operator**, such as the geometric mean, when a multi-factor metric must remain comparable across revisions.
3. **Controllers must target the submetric causing the deficit** through a causal actuator.
4. **Separate learning and control timescales** when the outer controller modifies the learner's environment or reward.
5. **Reward logic must agree with the directive and scoring function**.
6. **State representations must align with policy decision boundaries**.
7. **Size anti-synchronization noise from theory and measured uncertainty**, not unexplained tuning.
8. **Use causal multi-agent credit assignment** so local learners can improve population-level coordination.
9. **Prefer offline calibration when online identification is not identifiable or stable**.
10. **Use simulation as a gate before high-cost kernel implementation**, with failures driving architectural revision.

A proposed change that violates one of these principles requires explicit justification and new evidence.

---

## 15. Work-package program and phase gates

The complete research roadmap contains ten work packages. Codex must identify the relevant package before making a substantial change.

### WP1 — Linux Kernel Integration

**Goal:** establish ORCHESTRA as a native or extensible Linux scheduling component while preserving compatibility with existing scheduling classes.

Primary work:

- analyze Linux scheduling classes, run queues, task structures, domains, hooks, CFS/EEVDF, and real-time interactions;
- define insertion points;
- design the scheduler architecture;
- extend task and scheduler data structures;
- define control interfaces;
- build the hybrid scheduling framework;
- establish build, debug, trace, boot, rollback, and test infrastructure.

Exit gate:

- a bootable test kernel or approved scheduling-extension implementation;
- no regression in conventional and real-time fallback behavior;
- documented interfaces and data structures;
- automated build and recovery path;
- basic scheduling smoke tests pass.

### WP2 — Signal Bus and Kernel Communication Infrastructure

**Goal:** provide secure, hierarchical, low-latency signal acquisition, construction, publication, verification, synchronization, and lifecycle management.

Primary work:

- core/socket/NUMA/system hierarchy;
- hardware and kernel metric acquisition;
- versioned signal frames;
- read-only mapping or equivalent low-overhead access;
- cryptographic integrity and freshness;
- concurrent publication and coherent reads;
- expiry, retirement, recovery, and diagnostics;
- internal APIs for all later components.

Exit gate:

- consumers never observe torn accepted frames;
- stale, duplicate, replayed, and corrupted frames are rejected;
- measured publication and verification overhead is within the declared budget;
- key lifecycle is documented;
- failure and recovery tests pass.

### WP3 — Predictive Scheduling Engine

**Goal:** generate trusted short-horizon forecasts suitable for scheduling decisions.

Primary work:

- feature extraction;
- lightweight forecasting;
- independent calibration;
- parameter versioning;
- confidence estimation;
- prediction lifecycle;
- scheduler integration;
- accuracy, latency, and stability diagnostics.

Exit gate:

- held-out evaluation exists;
- prediction and observed-state fallback paths are tested;
- forecast latency fits the scheduling budget;
- stale predictions cannot affect decisions;
- negative and degraded-workload cases are reported.

### WP4 — Adaptive Process Scheduling

**Goal:** implement per-eligible-process adaptive scheduling while preserving coordination, fairness, responsiveness, and safety.

Primary work:

- state construction;
- action policy;
- learning and adaptation;
- coordination mechanisms;
- Hybrid Safety Layer;
- policy lifecycle and runtime management;
- diagnostics and debugging support.

Exit gate:

- action semantics are defined and tested;
- state/reward/directive consistency tests pass;
- real-time and exempt tasks bypass correctly;
- bounded fallback exists;
- no uncontrolled policy oscillation in stress tests.

### WP5 — Coordination Measurement and Feedback Control

**Goal:** continuously evaluate population behavior and safely optimize coordination through closed-loop control.

Primary work:

- S1–S4 computation;
- per-level coordination statistics;
- degradation detection;
- multi-actuator control;
- parameter optimization;
- multi-level coordination management;
- convergence, saturation, and stability monitoring;
- analytics.

Exit gate:

- metric tests include thundering-herd and false-good cases;
- actuator/submetric causal mapping is documented;
- controller bounds and rollback are implemented;
- two-timescale behavior is observable;
- no sustained controller saturation without an alert.

### WP6 — Kernel Instrumentation and Monitoring

**Goal:** make every major scheduler mechanism observable with controlled overhead.

Primary work:

- dispatch, preemption, migration, throttle, yield, sleep, and wake traces;
- signal generation and propagation traces;
- prediction timing and error traces;
- policy/action traces;
- S1–S4 and controller traces;
- performance profiling;
- logging, filtering, trace export;
- diagnostics and health monitoring;
- reproducible data collection.

Exit gate:

- tracing can be enabled selectively;
- overhead is measured and bounded;
- timestamps are comparable within the declared scope;
- exported data includes schema and metadata;
- instrumentation does not silently change scheduler behavior beyond the measured perturbation.

### WP7 — Experimental Evaluation and System Validation

**Goal:** evaluate correctness, performance, coordination, prediction, adaptation, resource use, robustness, and tradeoffs under realistic workloads.

Primary work:

- benchmark methodology;
- functional validation;
- performance evaluation;
- coordination assessment;
- predictor assessment;
- adaptation assessment;
- resource-utilization analysis;
- stress testing;
- comparison with Linux baselines;
- statistical analysis.

Exit gate:

- all experiments are reproducible from manifests;
- baselines use identical hardware and workload conditions;
- repeated runs and uncertainty are reported;
- warm-up, exclusions, and failures are disclosed;
- raw and processed data are traceable to commit and environment.

### WP8 — Scalability and Multi-Level Coordination

**Goal:** extend from a local kernel scheduler to multi-core, socket, NUMA, node, and cluster coordination.

Primary work:

- hierarchical scheduling responsibilities;
- multi-core signal coordination;
- NUMA locality and affinity;
- distributed signal aggregation and dissemination;
- clock, ordering, latency, and consistency handling;
- multi-level S1–S4 measurement;
- hierarchical control;
- scale testing;
- failure tolerance;
- large-scale optimization.

Exit gate:

- local scheduling remains safe when higher levels fail;
- hierarchy responsibilities and conflict resolution are explicit;
- remote-memory and communication costs are measured;
- synchronization assumptions are documented;
- scale limits and bottlenecks are reported honestly.

### WP9 — Security, Reliability, and Resilience Validation

**Goal:** validate trustworthiness and continued operation under attacks, faults, corruption, degraded resources, and prolonged execution.

Primary work:

- threat modeling;
- end-to-end trust-path validation;
- tamper, replay, spoof, stale-frame, and unauthorized-modification tests;
- component and communication fault injection;
- long-duration reliability tests;
- recovery and self-healing;
- availability and robustness metrics;
- runtime security monitoring;
- integrated attack-plus-fault testing.

Exit gate:

- threat model and trust boundaries are current;
- every detected failure has a safe response;
- mean and tail recovery times are measured;
- no unresolved critical vulnerability is accepted without an explicit risk decision;
- long-duration tests show no unaccounted leak or progressive instability.

### WP10 — System Optimization and Deployment Readiness

**Goal:** refine the integrated implementation into an efficient, maintainable, stable, configurable, and operationally supportable system.

Primary work:

- system-wide hot-path optimization;
- CPU, memory, cache, and communication optimization;
- stable default parameter selection;
- bounded runtime optimization;
- kernel-interface simplification;
- long-term stability validation;
- deployment configuration;
- technical and operational documentation;
- end-to-end regression validation;
- deployment-readiness assessment.

Exit gate:

- optimization does not weaken correctness, security, or coordination;
- sustained-run stability meets declared criteria;
- configuration and rollback are documented;
- operational diagnostics are sufficient for maintenance;
- remaining limitations are explicit;
- deployment-ready status is granted only through a formal review.

---

## 16. Phase ordering and dependency rules

Do not implement work packages as isolated checklists. Respect dependencies:

```text
Simulation evidence
      ↓
WP1 kernel foundation
      ↓
WP2 signal bus
      ↓
WP3 predictor
      ↓
WP4 adaptive scheduling
      ↓
WP5 measurement and control
      ↓
WP6 observability
      ↓
WP7 integrated evaluation
      ↓
WP8 scale-out
      ↓
WP9 security and reliability validation
      ↓
WP10 optimization and deployment readiness
```

Some work proceeds in parallel, but no downstream claim may bypass its upstream evidence gate.

Examples:

- Do not optimize an unvalidated hot path before its semantics are stable.
- Do not claim scalable coordination before local failure handling is correct.
- Do not deploy adaptive behavior without observability and fallback.
- Do not tune for `Q` alone before measuring latency, fairness, and overhead.

---

## 17. Recommended repository structure

Use a structure similar to:

```text
/
├── AGENTS.md
├── README.md
├── LICENSE
├── SECURITY.md
├── CONTRIBUTING.md
├── docs/
│   ├── architecture/
│   ├── adr/
│   ├── interfaces/
│   ├── threat-model/
│   ├── experiments/
│   ├── operations/
│   └── publications/
├── research/
│   ├── simulator/
│   ├── userspace/
│   ├── calibration/
│   ├── models/
│   └── experiments/
├── kernel/
│   ├── integration/
│   ├── signal_bus/
│   ├── predictor/
│   ├── adaptive/
│   ├── coordination/
│   ├── instrumentation/
│   └── selftests/
├── distributed/
│   ├── protocol/
│   ├── node_agent/
│   ├── synchronization/
│   └── fault_injection/
├── tools/
│   ├── build/
│   ├── trace/
│   ├── analysis/
│   ├── plotting/
│   └── environment/
├── experiments/
│   ├── manifests/
│   ├── workloads/
│   ├── baselines/
│   └── schemas/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── regression/
│   ├── security/
│   ├── stress/
│   └── statistical/
└── artifacts/
    ├── raw/
    ├── processed/
    └── reports/
```

Do not commit large raw traces or binaries without an approved artifact policy. Prefer manifests, checksums, and external artifact storage.

---

## 18. Architecture decision records

Create an ADR for decisions affecting:

- scheduler insertion point;
- scheduling-class precedence;
- signal-frame schema;
- cryptographic algorithm or key lifecycle;
- predictor model;
- state representation;
- reward function;
- compliance definition;
- coordination metric definition;
- actuator mapping;
- fallback policy;
- distributed consistency model;
- public experiment protocol.

Each ADR must contain:

1. context;
2. decision;
3. alternatives considered;
4. scientific or engineering evidence;
5. safety and security implications;
6. performance implications;
7. compatibility and migration plan;
8. status and superseding ADRs.

---

## 19. Coding standards

### 19.1 Kernel code

- Follow the Linux kernel coding style.
- Use kernel types and APIs; do not import userspace assumptions into kernel code.
- Avoid floating point in kernel paths.
- Avoid unbounded loops, dynamic allocation, blocking operations, or heavy cryptography in scheduler hot paths without a justified design.
- State locking, RCU, per-CPU, atomic, and memory-order assumptions explicitly.
- Prefer per-CPU data where it reduces contention and preserves semantics.
- Check all allocations and error returns.
- Keep scheduler hooks deterministic and bounded.
- Add tracepoints instead of ad hoc hot-path logging.
- Provide Kconfig help, build integration, and selftests.

### 19.2 Userspace systems code

- Use explicit feature-test macros.
- Check system-call failures.
- Use monotonic clocks for intervals and freshness.
- Keep data output separate from diagnostics.
- Clean up child processes, shared memory, mappings, file descriptors, and affinity changes.
- Never claim that self-throttling is identical to kernel dispatch control.

### 19.3 Python and analysis code

- Use typed functions for nontrivial modules.
- Pin dependencies for reproducible environments.
- Separate raw-data loading, validation, analysis, and plotting.
- Never mutate raw experiment data.
- Store analysis configuration with results.
- Report missing, excluded, and failed runs.
- Use deterministic seeds where scientifically appropriate.

### 19.4 Protocol code

- Use fixed-width fields and canonical byte order.
- Validate length, version, range, identity, freshness, and authentication before use.
- Fuzz parsers and verifiers.
- Never log secrets or raw keys.

### 19.5 Comments

Comments should explain:

- research rationale;
- invariants;
- concurrency behavior;
- safety boundaries;
- non-obvious mathematical choices;
- deliberate approximations.

Do not narrate obvious syntax.

---

## 20. Concurrency and memory-safety rules

Scheduling and signal publication are concurrent by design.

Every shared structure must specify:

- writer ownership;
- reader population;
- synchronization primitive;
- memory-order contract;
- lifetime and retirement rules;
- cross-CPU visibility;
- failure behavior.

Required practices:

- avoid torn accepted frames;
- do not place process-local pointers in shared portable structures;
- protect reader lifetime during updates;
- define sequence wrap behavior;
- test concurrent publication, read, expiry, key rotation, and teardown;
- use lockdep, KCSAN, KASAN, UBSAN, and relevant sanitizers where applicable;
- measure lock contention and cache-line bouncing;
- avoid false sharing in per-CPU or frequently updated statistics.

A race that only affects a metric is still a research-validity defect.

---

## 21. Testing strategy

### 21.1 Unit tests

Test at minimum:

- directive thresholds;
- state bucket boundaries;
- reward/directive agreement;
- epsilon schedule;
- Q-learning update;
- difference reward;
- geometric-mean metric;
- S4 mass-switch detection;
- predictor calibration and expiry;
- frame serialization;
- sequence and replay checks;
- HMAC verification;
- key epochs;
- controller bounds and actuator selection.

### 21.2 Integration tests

Test:

- acquisition → prediction → publication → verification → action;
- fallback from prediction to observation;
- fallback from ORCHESTRA to conventional scheduling;
- real-time bypass;
- controller interaction with learning;
- tracing and metric export;
- boot, shutdown, module unload, and recovery where supported.

### 21.3 Regression tests

Maintain named regressions for every failure discovered in the paper:

- metric blind spot;
- raw-product comparability failure;
- controller-target mismatch;
- reward contradiction;
- state-bucket misalignment;
- fixed exploration ceiling;
- online Kalman identifiability failure;
- insufficient anti-synchronization jitter;
- missing causal credit assignment.

A regression test must fail under the defective design and pass under the corrected design.

### 21.4 Security tests

Include:

- tampering;
- replay;
- duplication;
- reordering;
- stale frames;
- wrong key epoch;
- truncated frames;
- malformed values;
- spoofed source/tier;
- denial of signal service;
- key rotation race;
- compromised node scenarios.

### 21.5 Fault-injection tests

Inject:

- predictor failure;
- signal publisher failure;
- controller failure;
- CPU offline/online events;
- memory pressure;
- clock disturbance within the model;
- node disconnection;
- delayed or dropped messages;
- corrupted state;
- process and component crashes.

### 21.6 Stress and soak tests

Run prolonged tests for:

- memory leaks;
- counter overflow;
- sequence wrap assumptions;
- policy drift;
- controller oscillation;
- stale-state accumulation;
- trace-buffer pressure;
- scheduler latency degradation;
- recovery cycles.

---

## 22. Experimental methodology

### 22.1 Required baselines

Select baselines appropriate to the phase and document their configuration. Candidate baselines include:

- conventional Linux scheduling configuration;
- reactive ground-truth directive baseline used by the paper's simulator;
- non-predictive signal-driven variant;
- predictive variant without learning;
- learning variant without jitter;
- variant without difference reward;
- variant without controller;
- relevant Linux scheduling classes or `sched_ext` reference schedulers when applicable.

Do not describe a baseline as exact unless its semantics match the declared reference.

### 22.2 Workloads

Use multiple workload classes:

- compute-intensive;
- memory-intensive;
- cache-sensitive;
- I/O-intensive;
- network-intensive;
- interactive/latency-sensitive;
- mixed workloads;
- bursty and nonstationary workloads;
- thermal-pressure scenarios;
- real-time coexistence scenarios;
- NUMA and migration-sensitive workloads;
- distributed workloads for WP8.

Synthetic workloads are useful for causal control, but final claims require representative real workloads.

### 22.3 Metrics

Record at least where applicable:

- throughput;
- task completion time;
- response latency and tail latency;
- scheduling latency;
- context-switch count and cost;
- migration count and cost;
- fairness;
- starvation incidents;
- CPU utilization;
- memory and cache behavior;
- remote NUMA accesses;
- energy and thermal indicators;
- signal publication and verification latency;
- predictor MSE and confidence calibration;
- S1, S2, S3, S4, and Q;
- controller actions and saturation;
- recovery time;
- availability;
- security rejection counts;
- scheduler and instrumentation overhead.

Do not optimize or publish `Q` without conventional system metrics.

### 22.4 Repetition and statistics

For comparative claims:

- define independent run or seed;
- use multiple runs;
- report sample count;
- report mean and dispersion;
- include confidence intervals where appropriate;
- disclose warm-up and exclusion rules;
- preserve failed runs unless exclusion is predeclared;
- use paired designs when the same machine/workload trace can be reused;
- correct for multiple comparisons when conducting many hypothesis tests;
- separate exploratory analysis from confirmatory analysis.

### 22.5 Environment capture

Every experiment must record:

```text
commit hash
working-tree status
build configuration
kernel version and configuration
boot parameters
CPU model and topology
NUMA topology
memory size
frequency governor and turbo state
thermal environment where relevant
virtualization/container status
privileges and capabilities
background workload
command line and seed
start/end timestamps
dataset/workload versions
```

### 22.6 Data provenance

Each result must be traceable:

```text
source revision
  → build artifact
  → experiment manifest
  → raw trace
  → validation report
  → analysis script revision
  → processed table/figure
  → publication claim
```

Never manually edit raw traces.

---

## 23. Instrumentation rules

- Use structured events and versioned schemas.
- Use monotonic timestamps.
- Record tier and CPU/node identity.
- Distinguish observed state, predicted state, directive, recommendation, accepted action, and final dispatch outcome.
- Distinguish injected tamper events from per-reader rejection counts.
- Record controller decisions and the submetric that triggered each decision.
- Record fallback entry and exit reasons.
- Support sampling and selective tracing.
- Measure instrumentation overhead with tracing disabled and enabled.

Human-readable logs must not corrupt machine-readable datasets.

---

## 24. Performance rules

Correctness and safety precede optimization.

Before optimizing:

1. identify a measured bottleneck;
2. preserve a reproducible benchmark;
3. define a target metric and non-regression metrics;
4. capture a baseline;
5. make the smallest coherent change;
6. rerun correctness, security, and performance tests.

Never remove verification, bounds checks, or observability merely to improve a benchmark without an approved alternative.

Report tradeoffs. A change that improves throughput while harming tail latency, fairness, S4, energy, or recovery may not be an improvement.

---

## 25. Security and reliability process

Maintain a current threat model covering:

- malicious userspace process;
- compromised entitled process;
- compromised signal publisher;
- compromised node;
- replay and stale-state attacker;
- denial-of-service against signal dissemination;
- key compromise;
- malformed or adversarial metric inputs;
- policy poisoning;
- controller manipulation;
- side-channel and timing concerns where relevant.

Security-sensitive changes require:

- abuse-case tests;
- secret-handling review;
- failure-mode review;
- logging review;
- rollback plan;
- documentation update.

Reliability-sensitive changes require:

- fault injection;
- recovery-time measurement;
- repeated recovery cycles;
- resource-leak checks;
- verification that fallback remains available.

---

## 26. Documentation and publication integrity

Maintain clear separation among:

- architecture specification;
- implementation documentation;
- experiment protocol;
- results;
- interpretation;
- limitations;
- future work.

Use wording such as:

- “the simulator observed...”
- “the userspace prototype demonstrated...”
- “the kernel prototype implements...”
- “under the tested hardware and workloads...”
- “the result supports further investigation...”

Avoid unsupported wording such as:

- “ORCHESTRA is universally faster”;
- “100% secure”;
- “production-ready” before WP10 gates;
- “hard real-time” without a verified timing argument;
- “distributed implementation” when only local tiers exist;
- “paper reproduced” when protocols differ.

Preserve negative results. They are part of the scientific contribution.

Every figure and table must identify:

- experiment manifest;
- metric definition/version;
- sample count;
- aggregation method;
- uncertainty representation;
- exclusions;
- source data location.

---

## 27. Codex work protocol

### Before editing

1. Read this file and the nearest nested `AGENTS.md`.
2. Identify the relevant work package and maturity class.
3. Read the applicable paper, roadmap, ADR, interface, and test documents.
4. Inspect current implementation and tests.
5. Identify affected invariants, trust boundaries, hot paths, and result schemas.
6. Determine whether the request is canonical implementation, approximation, or exploratory research.

### While editing

1. Make the smallest coherent change.
2. Preserve canonical terminology.
3. Keep failure handling explicit.
4. Add or update tests with the implementation.
5. Add traceability for new runtime behavior.
6. Avoid unrelated refactoring.
7. Do not silently change metric, state, reward, directive, protocol, or baseline semantics.
8. Keep generated data out of source directories.

### After editing

1. Run the relevant build and static checks.
2. Run unit and integration tests.
3. Run security/fault tests if a trust or failure boundary changed.
4. Run a representative experiment if behavior or performance changed.
5. Validate machine-readable output schemas.
6. Check cleanup, unload, shutdown, and fallback behavior.
7. Update documentation, ADRs, manifests, and limitations.
8. Report exactly what changed, what evidence was produced, and what remains unvalidated.

---

## 28. Change review checklist

A reviewer or agent must answer:

### Architecture

- Which canonical component changed?
- Which work package owns the change?
- Does the architecture remain recognizable?
- Is the change canonical or exploratory?

### Correctness

- What invariant protects the behavior?
- Are threshold boundaries tested?
- Are concurrent reads/writes safe?
- Are failure and teardown paths tested?

### Learning/control

- Do reward, directive, state, and metric still agree?
- Is the learner/controller timescale relationship preserved?
- Does the actuator target the measured deficit?
- Are parameters bounded?

### Security

- Is the accepted signal authenticated, fresh, coherent, and correctly versioned?
- Are secrets protected?
- Is failure fail-closed and operationally safe?

### Experimentation

- Is the baseline semantically correct?
- Are the protocol and environment recorded?
- Are repetitions and uncertainty adequate?
- Are negative results retained?

### Claims

- Does wording match the maturity class?
- Are limitations explicit?
- Is any future work being presented as completed?

---

## 29. Definition of done

A change is complete only when all applicable conditions hold:

- the relevant specification or ADR is current;
- code builds with the project's strict warning policy;
- static analysis passes or findings are documented;
- unit, integration, regression, and relevant security tests pass;
- all normalized metrics remain finite and in range;
- signal verification remains fail-closed;
- real-time bypass and conventional fallback remain available;
- concurrent publication and consumption remain safe;
- no child, kernel resource, mapping, key, trace buffer, or allocation leaks;
- output schemas and experiment manifests are versioned;
- documentation matches actual behavior;
- performance claims have reproducible evidence;
- unsupported claims are absent;
- known limitations are updated;
- the change can be rolled back or safely disabled.

For deployment-readiness work, completion additionally requires:

- sustained-run validation;
- security review;
- recovery validation;
- configuration and operations documentation;
- compatibility assessment;
- formal readiness decision.

---

## 30. Prohibited shortcuts

Do not:

- treat the work-package roadmap as proof of implementation;
- replace the geometric-mean index with a raw product;
- remove S4;
- reward behavior that contradicts the directive;
- use state bins crossing policy thresholds without analysis;
- update an outer controller every tick at constant magnitude;
- reintroduce an unidentifiable adaptive Kalman estimator without new evidence;
- use unexplained random jitter;
- accept unauthenticated, stale, duplicated, or torn signal frames;
- authenticate compiler-dependent struct memory as a distributed wire protocol;
- let adaptive tasks override hard real-time classes;
- claim kernel control from userspace self-management;
- compare experiments with different workloads or environments as though paired;
- delete failed runs or negative findings to improve results;
- optimize only for Q;
- run destructive kernel experiments on production systems;
- store secrets or private keys in the repository;
- call the system deployment-ready before WP10 review.

---

## 31. Safe development environment

Kernel and scheduler work must use a recoverable environment:

- disposable VM, emulator, or dedicated test machine;
- serial console or equivalent recovery channel;
- known-good boot entry;
- automated timeout and reboot;
- filesystem snapshots where possible;
- watchdog for hangs;
- bounded worker counts and load;
- explicit privilege requirements;
- no production data.

A test that can hang, panic, starve, or thermally overload a machine must include a timeout and recovery procedure.

---

## 32. Initial priority order

Unless an approved milestone says otherwise, prioritize:

### P0 — Research fidelity and correctness

- complete source/spec traceability;
- canonical simulator regression suite;
- strict paper baseline;
- metric/reward/state/controller tests;
- reproducible multi-seed experiments;
- documented userspace-to-kernel semantic mapping.

### P1 — Kernel foundation and trusted signal path

- WP1 integration design and test environment;
- WP2 versioned signal frame;
- coherent publication and read path;
- integrity, freshness, key lifecycle, and fallback;
- instrumentation from the beginning.

### P2 — Predictor and adaptive policy

- held-out calibration pipeline;
- confidence and fallback;
- bounded adaptive actions;
- real-time bypass;
- policy lifecycle and diagnostics.

### P3 — Coordination and feedback

- kernel S1–S4;
- submetric-aware control;
- two-timescale enforcement;
- saturation and convergence monitoring.

### P4 — Evaluation and scale

- realistic workloads and Linux baselines;
- multi-core and NUMA experiments;
- distributed protocol and hierarchy;
- scale and fault testing.

### P5 — Security, reliability, and deployment readiness

- integrated threat and fault campaigns;
- long-duration validation;
- optimization with non-regression gates;
- configuration, operations, and readiness review.

---

## 33. Final instruction to Codex

Act as both a systems engineer and a research-methodology reviewer.

When asked to implement a feature:

- map it to the architecture and work package;
- state what is specified versus inferred;
- preserve safety, observability, and reproducibility;
- produce tests and evidence, not only code;
- report limitations without exaggeration.

The objective is not merely to make ORCHESTRA-OS run. The objective is to determine, with defensible evidence, whether predictive hierarchical signal coordination can become a correct, secure, scalable, and operational Linux scheduling architecture.
