# Signal-publication microbenchmark v1 — 2026-08-05 result

- Status: Descriptive exploratory evidence
- Claim class: Userspace-validated transport characterization only
- Protocol: [signal_publication_microbenchmark_v1.md](signal_publication_microbenchmark_v1.md)
- Artifact directory: `artifacts/test-results/2026-08-05/signal-publication-microbenchmark-v1/`
- Repository commit at capture: `0d20ffd3676c82946487788b8157740d5b21a342`
- Canonical source SHA-256: `8acbcc594beb4f2e1ab2489d83bb737784881aa4a6c74a4b62421a863ae0a8c8`

## What was run

The bounded v1 protocol with `gcc`, seed `20260805`, 2 repetitions, 1000
measured publications, 100 warm-up publications, and reader cohorts 1, 2, and 4.
Both publication modes were exercised:

- `legacy` — retained byte-wise reference transport
- `generation_stamped` — default ADR 0006 transport

## Outcome summary

All 12 invocations completed successfully under the harness bounds. Across every
cohort:

- `publisher_success_fraction` mean = 1.0
- `publisher_contention_fraction` mean = 0.0
- `publisher_generation_exhaustion_count` mean = 0.0
- `reader_hmac_failure_count` mean = 0.0
- `reader_retry_exhaustion_count` mean = 0.0 for generation-stamped cohorts

No invocation reported torn-frame acceptance, HMAC failure, regression,
duplicate acceptance, reader crash, or hang.

## Descriptive transport comparison (means across n = 2)

These numbers compare local userspace API behavior on the recorded host only.
They are not paired performance winners and must not be cited as kernel
scheduler evidence.

| Readers | Legacy publisher mean latency (ns) | Generation-stamped publisher mean latency (ns) | Legacy verified-read mean latency (ns) | Generation-stamped verified-read mean latency (ns) |
| --- | ---: | ---: | ---: | ---: |
| 1 | 4443 | 5699 | 4608 | 4883 |
| 2 | 6275 | 7639 | 5672 | 5776 |
| 4 | 8101 | 8425 | 7730 | 7986 |

At one reader, legacy snapshot-copy mean latency was lower (~117 ns vs ~243 ns),
but legacy also recorded non-zero snapshot instability (~2.0%) whereas
generation-stamped snapshot instability was 0.0% in this campaign.

At four readers, legacy exhibited one invocation with a very large verified-read
tail (`reader_verified_frame_max_latency_ns` = 506578) and higher retry burden
(`reader_retry_fraction` mean ≈ 0.144) than generation-stamped (≈ 0.015).

## Limitations

- `n = 2` per cohort; wide dispersion on some reader-side rates is expected.
- No CPU pinning, frequency control, or background-work suppression.
- Comparison design is `descriptive-unpaired-microbenchmark`.
- Snapshot-copy timing and verified-read timing are separate API measurements.
- This does not satisfy WP2 publication/verification budget gates for kernel work.

## Interpretation

The campaign supports continued userspace use of the generation-stamped transport
as the default implementation path: it preserved correctness invariants under
contention while avoiding the legacy transport's unstable snapshot copies and
large verified-read tail observed at four readers on this host.

It does **not** justify a performance superiority claim, a scheduler-time
budget claim, or promotion beyond bounded userspace-validated transport evidence.
