# Implementation execution plan for the 100% objective

This is the source-level plan that would be used after implementation authority is explicitly granted. It preserves the full objective and does not downgrade any checklist item to make the current prototype appear complete.

## Governing dependencies

The release-readiness plan requires the sequence WP1 → WP2 → WP3 → WP4 → WP5 → WP6 → WP7 → WP8 → WP9 → WP10. Downstream implementation and PASS claims cannot bypass an upstream gate.

## Ordered implementation tranche

### 1. Freeze interfaces and provenance

Authoritative requirements: release-readiness plan §§2, 12–15; ADRs 0001, 0002, 0006, 0007; checklist Phases 0–1.

Required deliverables:

- Freeze the kernel insertion/class-precedence decision and update the ABI/schema ADR.
- Define exact task/run-queue lifetime, locking, identity, generation, expiry, and fallback contracts.
- Add prediction horizon and explicit duplicate/replay/wrap semantics to the signal frame contract.
- Create an immutable release/build manifest, toolchain identity, source/BTF/header hashes, and rollback artifact lineage.

Acceptance evidence: a clean reproducible build from a pinned manifest, ABI static assertions, source-to-binary hashes, and a formal WP1 design review.

### 2. Complete the recoverable kernel foundation (WP1)

Current interfaces: `kernel/sched_ext/orchestra_scx_stage7.bpf.c`, `kernel/sched_ext/include/orchestra_bridge_v1.h`, `kernel/sched_ext/bridge/orchestra_loader.c`, and sched_ext lifecycle callbacks.

Required implementation work:

- Define the authoritative insertion and precedence behavior for normal, deadline, and RT scheduling classes.
- Make task admission/removal and identity lifetime race-safe across enable, enqueue, running, stopping, exit, and unload.
- Provide deterministic conventional-scheduler fallback and a tested global disable/detach path.
- Add boot/build/debug/recovery automation and regression tests for conventional, deadline, and RT behavior.

Acceptance evidence: exact-kernel build/boot, lifecycle matrix, no panic/oops/stall, fallback tests, known-good boot recovery, and no leaked maps/links/tasks.

### 3. Implement the trusted local signal substrate (WP2)

Current precursor: bridge control/directive maps and userspace stream structs in `orchestra_bridge_v1.h`; userspace HMAC/MAP_SHARED code remains outside the kernel scheduler.

Required implementation work:

- Define a kernel-safe fixed-width signal frame carrying schema, tier/source, sequence/epoch, state, prediction horizon, confidence, directive, and expiry.
- Define key ownership/provisioning, per-tier derivation, rotation overlap, revocation, compromise recovery, and secret erasure.
- Implement ordered bounds, schema, identity, sequence, freshness, authentication, duplicate, and replay checks.
- Add coherent publication/read retry diagnostics, last-known-good handling, parser fuzzing, epoch/rotation race tests, and publisher-loss recovery.
- Measure verification and publication p50/p95/p99/max cost and hot-path resource impact.

Acceptance evidence: accepted/rejected frame matrix, no torn accepted frames under contention, tamper/replay/duplicate/stale/wrong-source tests, key transition tests, fuzz results, and measured overhead.

### 4. Integrate predictor outputs with the trusted path (WP3)

Current precursor: userspace estimator and confidence tests; no kernel predictor output is exposed.

Required implementation work:

- Freeze an independent held-out calibration/evaluation split and versioned parameter artifact.
- Define no-look-ahead, recalibration, out-of-distribution, degraded, negative, and observed-state fallback behavior.
- Publish horizon/confidence/error metadata through the trusted frame and enforce stale/unsafe prediction exclusion.
- Measure predictor latency, CPU, memory, cache, and scheduler-path budget.

Acceptance evidence: held-out traces, artifact hashes, stable/increasing/decreasing/periodic/bursty regimes, negative cases, confidence fallback, and resource distributions.

### 5. Complete bounded adaptive kernel scheduling (WP4)

Current precursor: five directive action paths and per-task telemetry in `orchestra_scx_stage7.bpf.c`.

Required implementation work:

- Specify and implement all five action contracts across controller states and lifecycle conditions.
- Define admission/removal, safety-class precedence, RT/exempt bypass, conventional fallback, starvation/fairness limits, and bounded exploration.
- Complete SLEEP refresh/clear semantics; validate budget accounting and release semantics for THROTTLE; validate migration consequences rather than requests alone.
- Expose selected, requested, accepted, dispatched, effective, fallback, and final kernel outcomes with causal identity.

Acceptance evidence: full action × controller-state × directive-condition × lifecycle matrix, RT coexistence, fairness/starvation, repeated sleep/wake, migration and throttling stress, and fallback recovery.

### 6. Add kernel measurement, coordination, and controller (WP5)

Required implementation work:

- Expose versioned per-process/core/socket/NUMA/system S1, S2, S3, S4, and zero-preserving Q inputs.
- Define compliance and exemption rules, selected-versus-effective action accounting, temporal stability, burst/mass-switch penalties, and false-good tests.
- Implement bounded controller windows, deficient-submetric diagnosis, actuator causality, rate limits, saturation alerts, rollback, disable, and re-entry.
- Preserve the paper’s corrected temporal-stability requirement; do not report Q without all component values and formulas.

Acceptance evidence: valid S1–S4/Q decomposition, thundering-herd scenarios, controller convergence/oscillation/saturation/rollback tests, and causal actuator response.

### 7. Add selective kernel observability (WP6)

Required implementation work:

- Add versioned selective events for observations, frames, actions, dispatch, wake/preemption, migration, throttle, sleep, fallback, verifier, controller, recovery, and dropped records.
- Include schema, clock scope, identity, generation, reason, and provenance metadata.
- Measure tracing perturbation and reject experiments whose instrumentation exceeds the predeclared bound.

Acceptance evidence: complete event lineage for a workload, dropped-event accounting, coherent timestamps, and mean/tail CPU/memory/cache/latency overhead.

### 8. Establish valid experimental evaluation (WP7)

Required implementation/workflow work:

- Provide a portable ownership-validating benchmark runner without broad bpffs cleanup.
- Bound CPU, memory, I/O, and thermal load; preserve exact PIDs, affinity, warm-up, timeout, and scheduler state.
- Use identical CFS/scx_simple/ORCHESTRA protocols, counterbalanced order, at least five repetitions for strong claims, and predeclared primary outcomes.
- Collect latency, throughput, overhead, fairness, energy/thermal, robustness, raw traces, and exclusion reasons.

Acceptance evidence: all timed rows pass ownership, raw-to-report lineage, uncertainty/effect-size summaries, and no hidden outlier removal.

### 9. Implement hierarchy, NUMA, and distributed coordination (WP8)

Required implementation work:

- Define core/socket/NUMA/node/cluster responsibilities, conflicts, ordering, clocks, consistency, partitions, and local continuity.
- Implement multi-level signal/control isolation and downgrade behavior.
- Provide a genuine multi-NUMA host and distributed peer/test environment.

Acceptance evidence: 1/2/4/8/higher CPU matrix, multi-node locality/remote-memory costs, node/cluster fault isolation, communication overhead, and scaling limits.

### 10. Complete security, reliability, and deployment gates (WP9–WP10)

Required implementation/workflow work:

- Execute spoof/replay/corruption/authorization/key-transition and combined attack/fault campaigns.
- Exercise bridge/publisher/reader/predictor/policy/controller/storage/clock failures during activation and steady state.
- Run 10-minute, 60-minute, and longer soak tests with leak/livelock/starvation/epoch monitoring.
- Produce rollback, operator diagnostics, stable defaults, compatibility, downgrade, and formal readiness review artifacts.

Acceptance evidence: recovery-time distributions, availability/data-loss impact, long-run resource drift, signed/hashed release lineage, operational rollback proof, and formal WP10 approval.

## Verification rule

No implementation step is complete because code compiles or a smoke test passes. Each step must satisfy its stated acceptance evidence and update the 519-item checklist without suppressing negative results.

## Current authorization state

This plan is intentionally not executing source changes. The repository’s `AGENTS.md` declares the current session to be a testing/diagnosis campaign and forbids all implementation changes. Explicit authority to override that boundary is required before step 1 can become an implementation action.
