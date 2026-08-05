# Controller Safety State Machine

Status: **Implemented**

## Motivation

The previous ORCHESTRA-OS userspace prototype implemented a bounded multi-actuator feedback controller but operated as a memoryless reactive function. While it successfully adjusted jitter, switching penalties, and consensus blends based on recent metrics, it could not persistently track degradation, handle long-term saturation, or safely roll back from severe parameter drift. Furthermore, invalid frames (due to tampering, missing telemetry, or timeouts) risked corrupting the control loop history.

This document defines an explicitly stateful, observable, fail-safe control subsystem for the ORCHESTRA-OS signal architecture.

## State Definitions

The controller introduces six explicit, mutually exclusive states. All transitions and time spent in each state are measurable.

1. **NORMAL**: The controller receives valid accepted frames and applies adaptive updates according to the scheduled cadence and mathematical bounds.
2. **DEGRADED**: Coordination metrics (e.g., S3_global, S4) have persistently remained below the acceptable threshold (0.82) despite control efforts. Control updates continue, but the degradation is tracked for severity.
3. **SATURATED**: At least one actuator has hit its mathematical bound, and the targeted metric deficit persists beyond the specified saturation persistence limit. The controller warns that its authority is exhausted.
4. **DISABLED**: The controller has encountered repeated critical faults (e.g., invalid frames exceeding a threshold) or unrecoverable oscillation/saturation. No adaptive changes are applied.
5. **ROLLBACK**: Following a critical saturation or oscillation event, the controller atomically restores the last-known-good actuator vector to stabilize the population.
6. **RECOVERY**: A temporary quarantine state following a rollback, wherein the controller observes coordination quality without applying new adaptive changes. If metrics stabilize, it transitions back to `NORMAL`. Otherwise, it disables itself or rolls back again.

## Rolling-Window Semantics

Instead of reacting to instantaneous point-in-time metrics, the controller incorporates two fixed-size rolling windows:
* `controller_window_t`: Tracks `S3_global`, `S4`, and `S4_burst` over the last 10 accepted valid updates to average out noise.
* `oscillation_window_t`: Tracks the applied actuator vector (jitter, switch penalty) over the last 8 accepted updates to detect directional reversals and false tuning.

These windows use bounded compile-time sizes with deterministic wraparound. Invalid or rejected frames bypass the accepted history windows entirely, preventing poisoned state injection.

## Hysteresis and Persistence

Threshold transitions include hysteresis to prevent state chatter:
* Degradation requires at least 3 continuous updates in `NORMAL` where the moving average of `S3_global` or `S4` is below `CONTROLLER_THRESHOLD`.
* Recovery to `NORMAL` from `DEGRADED` or `SATURATED` requires the moving average to rise above the threshold for at least 3 continuous updates.
* `SATURATED` entry requires a bounded actuator parameter alongside a persistent metric deficit for 5 consecutive updates.

## Oscillation Detection

The controller records applied actuator movements. If the derivative of the actuator changes sign repeatedly without matching coordination improvement (4 or more reversals over the past 8 updates), an oscillation event is raised. Severe oscillation from `DEGRADED` automatically transitions the controller into `DISABLED`.

## Last-Known-Good Vector

A `last_known_good` vector is captured only when the controller has been in `NORMAL` for at least 5 updates without experiencing saturation or oscillation events. 

During `ROLLBACK`, the controller atomically applies the `last_known_good` vector. If no known-good vector was successfully recorded (e.g., fault at startup), the controller falls back to safe default constraints (`TRANSITION_REASON_DEFAULT_RECOVERY`).

## Actuator Bounds and Rate Limits

* **Jitter Sigma**: `[jitter_floor, 0.20]`
* **Switch Penalty**: `[0.0, 0.30]`
* **Consensus Blend**: `[0.0, 0.15]`

## Telemetry and Schema Strategy

To accommodate the complex diagnostic data (residence time, rollback causes, invalid frame counts, oscillation scores) without violating the strictly 83-column `v4` schema, a new explicitly versioned, append-only `orchestra.paper_cpu.metrics/v5` schema has been introduced.

The `v5` schema introduces 24 new columns detailing the exact numeric state of the controller, requested vs. applied limits, transition reasons, and suppression mechanisms.

## Computational Complexity

The entire update requires `O(W + A)` execution, where `W = 10` is the metric moving average calculation and `A = 3` represents the actuator variables.

No dynamic allocation, unbounded loops, or sleeping mechanisms occur inside the controller update logic.

## Safety and Claim Limitations

* This controller represents an exploratory control-theory safeguard. It does not replace the Linux scheduler (`sched_ext`).
* Fallbacks triggered by this controller merely stabilize userspace behavior guidelines; hard real-time tasks are exempt from this flow entirely.
