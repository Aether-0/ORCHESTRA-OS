# ORCHESTRA-OS 3-minute CPU benchmark

Date: 2026-08-14

## Scope

This is a userspace CPU-compute benchmark compiled from
`tools/benchmark/cpu_3min_bench.c`. It ran with four worker threads for 180
seconds under the normal host scheduler. No sched_ext program was loaded, no
task policy was changed, and no kernel modification was made.

## Result

```text
Target Duration:      180 seconds (3.0 minutes)
Actual Duration:      180.0011 seconds
Total Compute Ops:    278959563000 floating-point ops
Compute Throughput:   1549.77 Mops/sec (278.960 Gops total)
Total Context Sw:     1725896 switches (9588.25 ctx/sec)
Per-Thread Average:   387.44 Mops/sec
```

Progress remained monotonic through 15-second intervals, ending at
`1549.78 Mops/sec`.

## Interpretation

The benchmark completed without crash, timeout, or premature termination. The
measurement is a post-fix userspace baseline only. It is not an ORCHESTRA-versus-
CFS comparison, does not measure sched_ext overhead, and does not establish
physical-machine scheduler readiness.
