# ADR 0003: Metrics v3 conditioned coherence extension

- Status: Accepted — userspace telemetry implementation; experimental metric
- Date: 2026-08-04
- Work packages: WP5, WP6, WP7

## Context

The v2 `S3` is one global action-entropy score. It can penalize workers that
select different actions because their policy states legitimately differ.

## Decision

Metrics v3 retains v2 `S3` unchanged and emits it again as `S3_global`.
`S3_conditioned` is the eligible-worker weighted mean of per-state action
coherence, using current state-schema-v2 IDs. Empty groups have no weight; a
single-member group has coherence 1 because it has no within-group disagreement.
The reported historical Q remains based on `S3`, not the experimental metric.

## Consequences and limits

v2 and v3 CSV rows are not pooled in one statistical summary. Conditioned
coherence is a diagnostic for the current userspace state representation; it is
not a kernel-dispatch or scheduler-performance metric. Future experiments must
test whether state fragmentation or singleton-heavy cohorts make it misleading.
