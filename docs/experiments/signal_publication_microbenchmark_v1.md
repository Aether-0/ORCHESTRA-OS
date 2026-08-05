# Signal-publication microbenchmark v1

## Status and claim boundary

`orchestra.signal_publication.microbenchmark/v1` is a bounded, isolated
single-host userspace protocol for comparing the retained byte-wise reference
transport (`legacy`) with the default generation-stamped transport
(`generation_stamped`). It exercises the same canonical 128-byte payload,
separate 32-byte HMAC-SHA256 tag, publication API, coherent snapshot API, and
full verification API in both builds.

It is not a paper-CPU CSV experiment and does not alter metrics v2, v3, or v4.
It measures local authenticated signal-publication/read API behavior under the
recorded host conditions only. Linux remains the scheduler. The protocol does
not establish kernel scheduler behavior, scheduler dispatch compliance,
end-to-end ORCHESTRA performance, a scheduler-time budget, socket/NUMA
scalability, or a causal scheduling improvement.

The protocol is described here before any result is interpreted. A run creates
new evidence in a previously nonexistent directory; it must never overwrite
authoritative or earlier exploratory artifacts.

## Reproducible bounded command

Run from the repository root after building and testing the selected source:

~~~bash
python3 tools/benchmark/run_signal_publication_microbenchmark.py \
  --repository-root . \
  --output-dir /tmp/orchestra-signal-publication-microbenchmark-v1-20260804 \
  --cc gcc \
  --repetitions 2 \
  --iterations 1000 \
  --warmup 100 \
  --seed 20260804 \
  --max-readers 4 \
  --startup-timeout-ms 1000 \
  --max-runtime-ms 3000 \
  --drain-reads 4 \
  --timeout-sec 8 \
  --timeout-grace-sec 2
~~~

The output directory must not exist. The runner requires Linux and validates
all bounds before creating it. It compiles two fresh harness binaries with the
strict C warning policy, once with `ORCHESTRA_SIGNAL_PUBLICATION_LEGACY=1` and
once with `ORCHESTRA_SIGNAL_PUBLICATION_LEGACY=0`. A clean compile failure,
runtime timeout, interruption, malformed measurement, hash change, or failed
invariant is retained in the output and makes the run unsuccessful rather than
silently falling back.

The supported bounds are 2--10 repetitions, 100--200000 measured publication
attempts, 0--10000 warm-up publications, 1--16 configured readers,
10--5000 ms startup time, 100--10000 ms internal measurement time, and a
2--30 s external timeout. The external timeout must cover startup, measured
time, and the harness's 2000 ms bounded join-cleanup allowance. No root
privilege is required.

The runner uses the available CPU affinity to select the unique applicable
reader cohorts from 1, 2, 4, and the configured host-bounded maximum. It does
not pin threads, randomize mode order, control frequency scaling, or suppress
background work. Its comparison label is therefore
`descriptive-unpaired-microbenchmark`, even where a legacy and a
generation-stamped invocation use the same derived seed.

## Workload and bounds

Each invocation has one publisher and the selected number of reader threads.
The publisher performs the requested number of post-warm-up `publish_frame()`
attempts. Each reader repeatedly performs two distinct operations:

1. `selected_copy_canonical_frame(..., NULL)` for a coherent canonical-byte
   snapshot measurement; and
2. `read_verified_frame_with_diagnostics()` for a full frame-read result.

The two operations are deliberately separate calls and can observe different
generations or contention. The snapshot-copy timing is therefore not a
subtraction term from the verified-read timing, nor is it the snapshot used by
the subsequent verified read.

The harness uses `CLOCK_MONOTONIC`, bounded startup and measurement deadlines,
bounded drain reads, and bounded reader joins. A raw measurement must account
for all requested publisher outcomes, snapshot outcomes, reader outcomes, and
rejection reasons before it can enter a summary. A timing or clock failure,
deadline exit, generation exhaustion, incomplete publisher iteration count, or
unreconciled counter causes exclusion with preserved artifacts.

## Metrics and interpretation

Raw C-harness JSON is an aggregate over all reader threads in one invocation.
All latency values are monotonic elapsed nanoseconds around the named API call;
they are not per-call timestamp traces or latency percentiles.

### Publisher metrics

`publisher_attempts`, `publisher_successes`, `publisher_contended`, and
`publisher_generation_exhausted` partition publication attempts. The
`publisher_latency_sum_ns` and `publisher_latency_max_ns` fields time
`publish_frame()` attempts. They include canonical serialization/authentication
and the chosen transport operation but exclude payload construction performed
before the timing interval.

The derived invocation fields are:

- `publisher_attempts_per_sec` and `publisher_successes_per_sec`;
- `publisher_mean_latency_ns` and `publisher_max_latency_ns`;
- `publisher_success_fraction` and `publisher_contention_fraction`; and
- `publisher_contention_count` and `publisher_generation_exhaustion_count`.

### Snapshot-copy metrics

The raw fields `reader_snapshot_copy_attempts`,
`reader_snapshot_copy_successes`, `reader_snapshot_copy_empty`, and
`reader_snapshot_copy_unstable` partition the separate snapshot calls.
`reader_snapshot_copy_latency_sum_ns` and
`reader_snapshot_copy_latency_max_ns` include only successful
`SIGNAL_SNAPSHOT_COPIED` calls. A copied image is not yet deserialized,
freshness-checked, or HMAC-verified and must not be described as an accepted
frame.

The derived fields are:

- `reader_snapshot_copy_success_fraction`;
- `reader_snapshot_copy_empty_fraction`;
- `reader_snapshot_copy_unstable_fraction`;
- `reader_snapshot_copy_mean_latency_ns`; and
- `reader_snapshot_copy_max_latency_ns`.

The mean's denominator is successful snapshots, so it is null when no snapshot
succeeds. A null is an unavailable aggregate, not a zero-latency observation.

### Full verified-read metrics

The raw result partition is `reader_api_calls`, `reader_valid_reads`,
`reader_no_new_reads`, `reader_unstable_reads`, and `reader_invalid_reads`.
`reader_api_latency_sum_ns` and `reader_api_latency_max_ns` time every full
API call regardless of result. In particular, a `FRAME_NO_NEW` result returns
before full HMAC verification, so API timing must not be labelled HMAC time.

`reader_verified_frame_latency_sum_ns` and
`reader_verified_frame_latency_max_ns` time only `FRAME_VALID` calls. A valid
call includes its own coherent snapshot plus canonical decoding, field,
identity, sequence, freshness, epoch, and HMAC acceptance checks. Its timing
is still a local userspace API observation, not a kernel dispatch measurement.

The derived fields are:

- `reader_api_calls_per_aggregate_thread_sec` and
  `reader_valid_reads_per_aggregate_thread_sec`;
- `reader_api_mean_latency_ns` and `reader_api_max_latency_ns`;
- `reader_verified_frame_mean_latency_ns` and
  `reader_verified_frame_max_latency_ns`;
- `reader_valid_fraction`, `reader_retry_fraction`, and
  `reader_unstable_fraction`; and
- `reader_retry_exhaustion_count` and
  `reader_unstable_slot_observation_count`.

The rate denominators are the sum of individual reader elapsed times, so they
are aggregate-thread rates rather than a claim about system-wide throughput.
The verified-frame mean is null if no full call returns `FRAME_VALID`.
`reader_unstable_slot_observation_count` is a transport diagnostic for failed
snapshot confirmation (including post-pin/final confirmation mismatches), not
a count of accepted malformed frames.

### Rejection accounting

The runner exports `reader_invalid_frame_count` and one count for every
diagnostic reason:

- `reader_hmac_failure_count`;
- `reader_invalid_fields_count`;
- `reader_invalid_schema_count`;
- `reader_invalid_tier_count`;
- `reader_invalid_source_count`;
- `reader_invalid_directive_count`;
- `reader_invalid_sequence_count`;
- `reader_stale_frame_count`; and
- `reader_invalid_key_epoch_count`.

The reason counts must sum exactly to `reader_invalid_frame_count`. Under
concurrent legacy-reference operation a byte-wise snapshot can reach normal
validation as `FRAME_INVALID`; its safe rejection and reason are retained as
an outcome, not discarded. No such rejected frame is accepted as
`FRAME_VALID`. A clean non-tampered generation-stamped invocation requires
zero rejection reasons to be included. This is a bounded transport-robustness
observation only: it does not show a kernel-visible torn frame, scheduler
effect, or security proof.

## Statistical unit and summaries

One completed, hash-stable, validated bounded invocation is the only
statistical unit. Individual publisher attempts, snapshots, reader API calls,
and CSV fields within an invocation are correlated repeated observations; they
are not independent repetitions.

`processed/invocation_summaries.json` and
`processed/invocation_summaries.csv` contain exactly one derived row per
included invocation. `processed/summary.json` groups those invocation values
by publication mode and reader-count cohort and reports count, mean, sample
standard deviation when at least two invocations exist, minimum, and maximum.
The result is descriptive. It does not pool reader calls as samples, infer a
population effect, or establish a paired comparison.

## Artifacts and provenance

For an output directory `OUT`, the runner preserves:

- `OUT/provenance.json`: schema identifier, controls, environment, reader
  cohorts, canonical and microbenchmark source hashes, and start time;
- `OUT/build/compile_legacy.log`,
  `OUT/build/compile_generation_stamped.log`, and
  `OUT/build/build_records.json`: exact compiler command/output and binary
  hashes;
- `OUT/runs/*.stdout.json`, `*.stderr.log`, and `*.json`: every command,
  seed, timestamps, wall/user/system CPU time, background-load snapshots, raw
  measurement, validation result, source/binary hashes after the run, and
  inclusion or exclusion reason;
- `OUT/processed/invocation_summaries.json` and `.csv`: one row per included
  independent invocation;
- `OUT/processed/summary.json`: cohort-level descriptive summaries; and
- `OUT/benchmark_result.json`: expected, attempted, validated, and excluded
  invocation counts; run status; end time; input/binary hashes; and processed
  output locations.

Failed, timed-out, interrupted, and excluded invocations keep their logs and
per-run records. They are not removed to improve a summary. The source and
binary hashes are checked before and after each invocation, so a changed input
or binary is an explicit exclusion.

## Relationship to stress and integration tests

The microbenchmark is not a replacement for correctness tests. The ordinary
test target runs both layers:

~~~bash
make test
~~~

For focused execution, use:

~~~bash
./tests/unit/run.sh
./tests/integration/run.sh
~~~

The unit script runs the bounded concurrent generation-publication stress test
under GCC AddressSanitizer/UndefinedBehaviorSanitizer and, when available,
under Clang's strict warning policy. The integration script runs the separate
shared-mapping/read-only/lease-contention and bounded teardown checks. Those
tests cover specified interleavings and safety outcomes; the microbenchmark
adds local descriptive API timing and provenance, not a stronger correctness
or performance claim.

## Non-claims and follow-up work

This protocol does not provide tail percentiles, CPU isolation, frequency
control, randomized mode order, cache analysis, NUMA analysis, long-duration
generation-wrap evidence, process-crash recovery evidence, parser fuzzing,
security validation, or a kernel hot-path budget. It also does not establish
that either transport improves the Linux scheduler or an ORCHESTRA policy.

Any future performance conclusion needs a separately reviewed experiment with
appropriate host control, replication, uncertainty analysis, and an explicit
claim boundary. Existing paper-CPU evidence remains historical and must not be
rewritten or silently pooled with this isolated transport experiment.
