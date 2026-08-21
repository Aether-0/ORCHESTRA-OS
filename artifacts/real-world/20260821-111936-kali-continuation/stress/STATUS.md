# Stress phase status

The repository stress script was inspected but not executed in this continuation.

`stress_suite.sh` derives `STRESS_MB` as half of total RAM and, because `/usr/bin/stress` is installed, starts two VM workers with `--vm-bytes ${STRESS_MB}M`. This 15 GiB host would therefore be asked to allocate approximately 15.4 GiB before CPU, kernel, and desktop overhead. The script has no safe memory-size argument. Running it would violate the campaign safety boundary, so the CFS and ORCHESTRA stress-script items are `BLOCKED_FOR_SAFETY` / `BLOCKED_INSUFFICIENT_OBSERVABILITY` in the results.

No script or source file was changed. The existing prior-campaign CFS smoke result remains archived separately and is not counted as a new continuation run.
