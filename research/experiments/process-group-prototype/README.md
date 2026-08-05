# ORCHESTRA-OS process-group prototype (Exploratory)

**Claim class: Exploratory.** This directory is non-canonical. It implements
process groups, group runnable budgets, and coordinator-driven restart behavior
that the approved ORCHESTRA architecture explicitly excludes. Do not build,
measure, or describe it as part of canonical ORCHESTRA-OS.

This is a **real Linux userspace experiment**, not a browser simulation. It creates real worker processes, consumes real CPU time, reads real Linux resource statistics from `/proc`, and coordinates workers through shared memory.

It does **not** replace the Linux kernel scheduler. Linux still performs final dispatch, preemption, fairness and safety. The prototype tests the proposed control architecture before a kernel implementation.

## Implemented

- Real worker processes created with `fork()`
- Shared control frame using `mmap(MAP_SHARED)`
- Real CPU utilization from `/proc/stat`
- Real memory pressure from `/proc/meminfo`
- Short-horizon CPU prediction
- Four process groups:
  - interactive
  - compute
  - I/O
  - background
- Per-process actions:
  - `RUN`
  - `SLEEP`
  - `YIELD`
  - `MIGRATE` using `sched_setaffinity()`
  - `THROTTLE`
- Group-level runnable budgets
- Per-worker anti-synchronization jitter
- Coordination components `S1`, `S2`, `S3`, `S4`, and geometric-mean `Q`
- Heartbeat-based worker failure detection and automatic restart
- CSV output for experimental analysis

## Build

```bash
make
```

Requirements:

- Linux
- GCC or Clang
- GNU Make
- No root permission required for the default experiment

## Run

Basic 30-second group-layer experiment:

```bash
./orchestra_real_cpu --workers 16 --duration 30 > results_group.csv
```

Direct per-process mode without group budgets:

```bash
./orchestra_real_cpu --workers 16 --duration 30 --direct > results_direct.csv
```

Inject a real worker crash after 10 seconds and test recovery:

```bash
./orchestra_real_cpu --workers 16 --duration 30 --fault-after 10 > results_fault.csv
```

Run until `Ctrl+C`:

```bash
./orchestra_real_cpu --duration 0
```

## Compare the group idea

Run the same workload twice:

```bash
./orchestra_real_cpu --workers 24 --duration 60 > group.csv
./orchestra_real_cpu --workers 24 --duration 60 --direct > direct.csv
```

Compare these columns:

- `cpu_now`
- action counts
- `S2` compliance
- `S3` coherence
- `S4` temporal stability
- `Q`

The output is printed once per controller tick.

## Safety

The program intentionally creates CPU load. Start with 8 or 16 workers. Stop it with `Ctrl+C` if the system becomes slow.

Do not run it on production machines. Use a development workstation, VM, or dedicated test host.

## Important limitation

This program validates a userspace control design on real hardware. It cannot prove kernel-level scheduling gains because:

- Linux CFS/EEVDF remains the actual scheduler.
- Userspace control has higher latency than scheduler-tick code.
- It does not implement a kernel signal bus, HMAC key management, a Linux scheduling class, or hard real-time guarantees.

A true kernel experiment should come after this step, preferably first through `sched_ext`/eBPF or a minimal kernel module before attempting a new in-kernel scheduling class.
