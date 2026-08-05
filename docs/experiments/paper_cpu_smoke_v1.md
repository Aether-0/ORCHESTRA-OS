# Paper CPU userspace smoke protocol v1

## Status and question

This is a bounded **userspace-validated** smoke protocol for the canonical
`orchestra_paper_cpu_demo`. It asks whether the baseline and ORCHESTRA modes
complete safely, emit the strict metrics-v2 schema, and preserve their declared
coordination, controller, and provenance invariants on one Linux host.

The two mode summaries are **descriptive, unpaired, and endogenous**. Each mode
changes the host CPU signal that it subsequently observes. The protocol does
not estimate a causal mode effect and must not support kernel-scheduler,
hard-real-time, security, scalability, or general performance claims.

## Inputs and bounded controls

The approved smoke manifest is
`experiments/manifests/paper_cpu_smoke_v1.json`. It declares:

- four workers and zero real-time-exempt workers;
- a four-second measured phase after one second of calibration;
- a 100 ms configured interval;
- three fixed seeds per mode;
- ten warm-up ticks excluded before analysis;
- baseline followed by ORCHESTRA for each seed, never concurrently;
- an external 12-second timeout, two-second termination grace, and niceness
  increment of 10.

The harness rejects duration zero, more than 30 seconds, fewer than two or more
than ten repetitions, real-time-exempt workers, unsafe worker counts, duplicate
or missing seeds, and an output directory that already exists.

## Run

Build the userspace binary first, then pass that exact artifact and its source
to the harness. Keep generated data outside the source tree unless an in-tree
artifact location has been explicitly chosen for a controlled reason.

```bash
make -C orchestra_paper_cpu_demo

python3 tools/benchmark/run_paper_cpu_benchmark.py \
  --manifest experiments/manifests/paper_cpu_smoke_v1.json \
  --schema experiments/schemas/paper_cpu_metrics_v2.json \
  --binary orchestra_paper_cpu_demo/orchestra_paper_cpu \
  --source orchestra_paper_cpu_demo/orchestra_paper_cpu.c \
  --repository-root . \
  --output-dir /tmp/orchestra-paper-cpu-smoke-v1
```

The output directory is mandatory and must not exist. Use a new path for every
attempt. Do not run this command with `sudo`; the manifest deliberately disables
the `SCHED_FIFO` attempt.

## Captured evidence

The top-level `provenance.json` records the full manifest, source and binary
SHA-256 hashes, binary help output, UTC time, Git status or an explicit
`not-a-git-worktree` state, uname, lscpu, memory, frequency governor/turbo
controls, virtualization/container evidence, privilege and capability masks,
kernel command line, and initial background load.

For each invocation, `runs/` retains:

- unmodified stdout CSV and stderr log;
- complete argv and shell-escaped command;
- seed, repetition, mode, UTC start/end, return code, timeout status, and wall
  duration;
- whole-invocation child user/system CPU time, voluntary/involuntary context
  switches, and minor/major page faults from `RUSAGE_CHILDREN` deltas;
- before/after host load;
- raw-artifact hashes;
- all validation errors and the predeclared exclusion reason.

Failed, timed-out, interrupted, or malformed runs remain in `runs/` and are not
silently deleted. They are excluded from processed statistics under the rule
declared before execution.

The resource deltas are conventional, whole-process userspace observations.
They are not throughput, scheduler latency, verified per-worker attribution, or
evidence of kernel-scheduler speed.

## Validation contract

The external schema `orchestra.paper_cpu.metrics/v2` defines one exact,
ordered, 40-column CSV header. The runner also fixes this header internally so
that replacing the schema file cannot weaken validation. It verifies:

- finite/ranged values and strict field types;
- sequential ticks and monotonic rejection/deadline counters;
- the exact row count and a minimum wall duration implied by the manifest;
- action counts summing to eligible workers;
- S2 matching exact directive compliance;
- S3 matching normalized entropy reconstructed from action counts;
- `Q = (S1*S2*S3*S4)^(1/4)`, with exact zero whenever any factor is zero;
- observed versus predicted decision-source labeling;
- baseline exclusion of prediction and consensus;
- controller updates only each 20 ORCHESTRA ticks;
- controller step, causal S3/S4 reason, decaying beta, parameter propagation,
  on-cadence actuator equations, saturation flags, and actuator bounds;
- source and binary hashes remaining unchanged throughout the campaign.

The nonzero-Q reconstruction tolerance is `1e-7`, solely to accommodate the
eight-decimal CSV representation. It does not permit the former `Q=0.001`
floor when any component is zero.

## Processing and statistics

Only schema-valid, successful, hash-stable invocations with observations after
the declared warm-up enter `processed/`. Tick rows are not treated as
independent samples. The statistical unit is one invocation summarized after
warm-up.

Outputs include:

- `processed/validated_rows.csv`, containing post-warm-up rows with run IDs;
- `processed/run_summaries.csv`, one row per accepted invocation;
- `processed/mode_summary.csv`, long-form per-mode statistics;
- `processed/summary.json`, the same statistics and interpretation metadata.

For every metric and mode, the runner reports independent-run count, mean,
sample standard deviation, and a two-sided 95% Student-t confidence interval
when at least two runs are available. It intentionally computes no baseline
minus ORCHESTRA effect, speedup, or hypothesis-test result.

## Interpretation boundary

Acceptable wording is limited to statements such as: “Under the recorded host
and smoke workload, the userspace prototype completed N validated invocations
and produced the following descriptive coordination measurements.”

The outputs cannot establish that ORCHESTRA is faster than Linux, replaces
Linux dispatch, provides hard-real-time guarantees, reproduces the paper’s
controlled 3,000-tick simulation, or is experimentally validated beyond this
documented userspace protocol.
