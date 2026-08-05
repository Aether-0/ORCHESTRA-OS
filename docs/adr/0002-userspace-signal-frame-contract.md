# ADR 0002: Userspace Canonical Signal Frame and Verification Contract

- Status: Accepted - implemented in the current userspace prototype
- Date: 2026-08-03
- Amended: 2026-08-04 for the ADR 0006 publication-transport supersession
- Decision class: Specified
- Implementation status: Userspace implementation and focused tests exist; WP2 validation is incomplete
- Maturity scope: Single-host userspace prototype only
- Work package: WP2 Signal Bus and Kernel Communication Infrastructure
- Related: ADR 0001, Userspace State, Metric, Reward, and Controller Contract; ADR 0006, Generation-Stamped Signal Publication
- Supersedes: None
- Superseded by: ADR 0006 for the coherent-publication transport only; the canonical wire, authentication, verification, and freshness contract remains active here

## 1. Context

The ORCHESTRA-OS paper specifies a signed shared signal with a monotonic sequence and rotating keys, but reports a pre-kernel simulation. It assumes that a verifier already has the correct key and does not solve provisioning, revocation, node membership, compromise recovery, or distributed key lifecycle.

The first userspace demo authenticated the native bytes of a C structure. The current implementation no longer does so: it serializes a fixed 128-byte payload, authenticates that complete payload with a separate 32-byte HMAC-SHA256 tag, and publishes the resulting 160-byte canonical image through the generation-stamped transport defined by ADR 0006. This ADR records the implemented wire and verification contract rather than a future protocol design.

The contract is deliberately local and experimental. It defines one producer, one monotonic clock domain, one core-local tier identifier, fork-inherited key material, and userspace action approximations. It is not a Linux kernel ABI, scheduler-class interface, distributed protocol, production key-management design, or security-validation result.

## 2. Decision

### 2.1 Schema, payload size, tag, and byte order

The implemented signal payload uses schema version `1` and is exactly 128 bytes. The authentication tag is a separate, full 32-byte HMAC-SHA256 value; it is not part of the 128-byte payload.

All integer fields are unsigned and serialized big-endian. Every floating-point field is serialized by copying its binary64 storage bits into an unsigned 64-bit integer and writing those bits big-endian. The implementation has a compile-time assertion that `double` and `uint64_t` have the same storage size. It serializes fields individually and never authenticates native structure padding.

The implemented fixed identities are:

- magic: `0x4f524348`, the ASCII bytes `ORCH`;
- signal schema: `1`;
- state schema: `2`;
- tier: `1`, named `SIGNAL_TIER_CORE_LOCAL` in the implementation; and
- source: `0`, named `SIGNAL_SOURCE_LOCAL`.

No other tier, source, signal schema, or state schema value is accepted by this implementation.

### 2.2 Canonical 128-byte authenticated payload

| Offset | Size | Field | Implemented encoding and acceptance contract |
| ---: | ---: | --- | --- |
| 0 | 4 | `magic` | Unsigned big-endian; exactly `0x4f524348` |
| 4 | 4 | `schema_version` | Unsigned big-endian; exactly `1` |
| 8 | 4 | `tier` | Unsigned big-endian; exactly `1` (core-local) |
| 12 | 4 | `source_id` | Unsigned big-endian; exactly `0` (local source) |
| 16 | 8 | `sequence` | Unsigned big-endian; nonzero |
| 24 | 8 | `monotonic_ns` | Unsigned big-endian producer `CLOCK_MONOTONIC` timestamp |
| 32 | 8 | `max_age_ns` | Unsigned big-endian; `1..10,000,000,000` ns |
| 40 | 4 | `key_epoch` | Unsigned big-endian; exactly `floor(sequence / 100)` after conversion to `uint32_t` |
| 44 | 4 | `directive` | Unsigned big-endian; `0=RUN`, `1=SLEEP`, `2=MIGRATE`, `3=THROTTLE`, `4=YIELD` |
| 48 | 4 | `state_schema_version` | Unsigned big-endian; exactly `2` |
| 52 | 4 | `prediction_used` | Unsigned big-endian; `0` or `1` |
| 56 | 8 | `cpu_now` | Binary64 bits, big-endian; finite and numerically in `[0,1]` |
| 64 | 8 | `cpu_pred` | Binary64 bits, big-endian; finite and numerically in `[0,1]` |
| 72 | 8 | `decision_cpu` | Binary64 bits, big-endian; finite and numerically in `[0,1]` |
| 80 | 8 | `memory_pressure` | Binary64 bits, big-endian; finite and numerically in `[0,1]` |
| 88 | 8 | `thermal_proxy` | Binary64 bits, big-endian; finite and numerically in `[0,1]` |
| 96 | 8 | `confidence` | Binary64 bits, big-endian; finite and numerically in `[0,1]` |
| 104 | 8 | `jitter_sigma` | Binary64 bits, big-endian; finite and in `[0,0.20]` |
| 112 | 8 | `switch_penalty` | Binary64 bits, big-endian; finite and in `[0,0.30]` |
| 120 | 8 | `consensus_blend` | Binary64 bits, big-endian; finite and in `[0,0.15]` |

The serializer and deserializer both require their cursor to end at byte 128 and abort the process if the compiled field sequence does not do so. Because the bus contains a fixed-size array rather than a variable-length parser, schema 1 has no serialized length field.

NaNs and infinities are rejected by field validation. Numeric range comparisons accept either binary64 representation of zero, including negative zero; schema 1 does not impose an additional unique-zero encoding rule. The payload contains no flags, prediction-horizon field, run identifier, pointers, handles, authentication tag, or secret material.

### 2.3 Authentication and key derivation

For a payload carrying epoch `e`, the implementation derives:

```text
epoch_message = uint32_big_endian(e)
epoch_key     = HMAC-SHA256(master_key, epoch_message)
tag           = HMAC-SHA256(epoch_key, canonical_payload[0..127])
```

The derivation input is exactly the four-byte big-endian epoch. It does not include a label, tier, source, schema, or run identifier. Tier, source, schema, and all other payload fields are nevertheless covered by the second HMAC because the complete 128-byte payload is authenticated.

The publisher assigns `key_epoch = floor(sequence / 100)`, and field validation requires that exact relationship. There is no previous-epoch overlap window. The derived epoch key is cleared with `explicit_bzero` after signing or verification. Tag comparison accumulates differences over all 32 bytes before returning.

At process startup, the parent obtains a 256-bit master key from `/dev/urandom` before forking workers. Adaptive workers inherit the master and derive epoch keys locally. The master is cleared with `explicit_bzero` on implemented orderly and handled-error teardown paths.

### 2.4 Coherent publication and snapshot

The canonical shared image is unchanged: the 128-byte canonical payload followed
by the separate 32-byte HMAC-SHA256 tag. The default publication transport is
defined in ADR 0006. It represents those 160 canonical bytes as twenty atomic
`uint64_t` words in each of two slots. This is an internal userspace transport
representation only: the HMAC input remains the canonical byte serialization,
not native structure memory or host-endian fields.

The parent is the single frame publisher. For an ordinary publication it
serializes and signs the same payload. For explicit tamper injection, it signs
the original payload, changes `cpu_pred` in a copy, then publishes the changed
canonical payload image with the original tag so verification intentionally
fails.

The two slots are selected by a single atomic token:

```text
token = (generation << 1) | active_slot
```

Token zero is uninitialized. Generations begin at one and are limited to
`UINT64_MAX >> 1`; reaching that bound safely stops further publication rather
than allowing generation/token reuse. A slot's sequence is `generation << 1`
while complete and `(generation << 1) | 1` while the writer owns it.

Reader ownership is kept outside the read-only canonical signal bus in a
companion `MAP_SHARED` reader-gate mapping. It has one atomic `access_state`
per slot: its high bit is the writer-exclusive lease and its remaining bits are
the reader-pin count. The mapping contains no payload, HMAC, key, policy, or
scheduler state. Workers map the canonical token/slot/payload bus read-only;
only the two bounded gate entries remain writable for reader pinning.

The ISO C11 memory model does not itself define atomic synchronization across
processes. This userspace implementation is scoped to Linux/POSIX
`MAP_SHARED | MAP_ANONYMOUS` mappings with lock-free selected atomics. Before
workers start, it checks the required selected publication and gate objects and
representative shared-control atomic types with `atomic_is_lock_free`; failure
terminates the run rather than selecting a non-atomic fallback. This is a
checked platform assumption, not a portable ISO C proof of inter-process atomic
behavior.

The writer chooses only the inactive slot. It first acquires that slot's
writer-exclusive gate lease only when its reader-pin count is zero. It then
marks the slot in progress, writes the complete 20-word image, marks the slot
complete, releases the new token, and then releases the gate lease. It refuses
bounded contention rather than waiting for or overwriting a pinned slot. A
refused or exhausted publication does not make a partial frame visible; readers
can only continue with a previously committed frame and the existing
freshness/last-known-good behavior remains applicable.

If a reader dies while pinned or a publisher dies while holding a writer lease,
that gate can remain nonzero. The current prototype has no production lease
reclamation: this is an availability loss that results in bounded contention
refusal and the existing last-known-good or fallback behavior. The explicit
gate resets in stopped-process integration tests are test-only cleanup, not a
crash-recovery mechanism.

A reader makes at most ten snapshot attempts. It acquires the token, chooses
the token's slot, obtains a low-bit reader pin only while that gate's high-bit
writer lease is clear, and then re-acquires and confirms the same token before
copying a complete matching-generation image. It performs final acquire checks
of both token and slot sequence before unpinning and accepting the copied words.
If a token/slot/generation confirmation fails, the reader unpins and retries.
Acquire/release ordering connects complete-slot writes to the released token,
while the gate lease makes checking and pinning race-free and prevents a writer
from reusing the selected slot while the reader copies it. Thus a reader accepts
neither an in-progress nor a torn image.

If all ten attempts fail, `read_verified_frame` returns `FRAME_UNSTABLE`.
Retry exhaustion remains distinct from both `FRAME_NO_NEW` and verified
acceptance and does not bypass the normal schema, identity, sequence,
freshness, epoch, or HMAC checks.

The previous byte-wise atomic publication implementation remains available only
as the compile-time `ORCHESTRA_SIGNAL_PUBLICATION_LEGACY` test/reference mode.
It preserves the canonical serialization and HMAC verification contract, but
it is not the default research transport and is not a performance baseline.

Before workers are created, the program checks the selected shared atomic
objects needed by the chosen transport. The canonical bus can remain read-only
in workers because reader pins use only the separate gate map. Failure of the
required atomic support ends the run rather than silently using non-atomic
shared-frame access.

### 2.5 Implemented verification order and result semantics

After obtaining a coherent snapshot, a consumer follows this exact order:

1. deserialize the 128-byte payload;
2. validate magic, signal schema, state schema, directive, `prediction_used`, `max_age_ns`, and all numeric bounds;
3. validate the fixed tier and source identity;
4. require a nonzero sequence and compare it with the worker's last accepted sequence;
5. for a greater sequence, reject a future timestamp or age exceeding `max_age_ns`;
6. require the exact sequence-to-epoch relationship;
7. derive the declared epoch key, recompute HMAC-SHA256 over all 128 canonical payload bytes, and compare the separate 32-byte tag; and
8. return the deserialized payload as `FRAME_VALID` only after every applicable check succeeds.

The sequence outcomes are deliberately distinct:

- `sequence < last_accepted_sequence` returns `FRAME_INVALID`;
- `sequence == last_accepted_sequence` returns `FRAME_NO_NEW`; and
- `sequence > last_accepted_sequence` may proceed to freshness and authentication.

Transport retry exhaustion is also distinct: it returns `FRAME_UNSTABLE`
before deserialization, so it has no sequence, freshness, or authentication
classification and cannot be treated as an accepted frame.

An equal-sequence frame is classified as no new work after schema/bounds,
identity, and nonzero-sequence validation; its freshness, epoch schedule, and
HMAC are not rechecked. A coherent-snapshot retry exhaustion instead returns
`FRAME_UNSTABLE`. A sequence gap is accepted if the greater frame passes every
remaining check, but the size of that gap is not emitted as dedicated
telemetry.

On `FRAME_VALID`, the adaptive worker updates its process-local
`last_sequence` and last-known-good payload, constructs state, performs any
preceding Q update, and selects a new action. It then publishes the selected
action, previous action, fallback flag, and `accepted_sequence` together under
the per-worker decision version. `FRAME_INVALID`, `FRAME_NO_NEW`, and
`FRAME_UNSTABLE` do not perform a new policy or Q-table transition; expiry may
separately publish the bounded fallback decision while retaining the last
accepted sequence.

The parent still emits coordination telemetry for incomplete or rejected-frame
samples, allowing lost reach to reduce S1. It assigns difference rewards and
runs the outer controller or consensus only when every configured non-exempt
worker has coherently published acceptance of the current sequence. Thus an
invalid frame or unstable transport read may be measured as a coordination
failure but cannot change a later reward, policy table, or actuator vector.

### 2.6 Prediction selection, last-known-good behavior, and fallback

Prediction fallback and signal-loss fallback are separate mechanisms.

For every newly published valid frame, `decision_cpu` is selected before signing:

- ORCHESTRA mode uses `cpu_pred` only when confidence is finite and at least `0.50`;
- lower or non-finite confidence selects observed `cpu_now`; and
- baseline mode always selects observed `cpu_now`.

`prediction_used` records that choice in the authenticated payload and CSV output. This is observed-state fallback for predictor confidence; it does not bypass signal-frame verification.

Each adaptive worker retains its most recently accepted payload as last known good. When a read returns `FRAME_INVALID`, `FRAME_NO_NEW`, or `FRAME_UNSTABLE`:

- if a last-known-good payload exists and its authenticated `max_age_ns` has not expired, the worker keeps its previously selected action and does not make a new decision from the rejected, absent, or unstable frame;
- if no last-known-good payload exists, its timestamp is now in the future, or its age exceeds its `max_age_ns`, the worker records `THROTTLE` and sets `fallback_active`; and
- a later `FRAME_VALID` decision clears `fallback_active` and re-enters the adaptive path.

The fallback action is the userspace `THROTTLE` approximation implemented as bounded busy work followed by sleep. It is not a transition to a different Linux scheduling class and is not a conventional Linux scheduler fallback. There is no independently acquired worker-local observation fallback after signal loss.

Hard-real-time-designated workers enter a separate bypass loop and do not enter this adaptive verification or fallback chain. An unsuccessful `SCHED_FIFO` attempt is reported on stderr, but the worker remains classified as exempt and continues its deterministic userspace loop under the Linux policy actually granted.

### 2.7 Implemented telemetry

Machine-readable CSV currently exposes:

- tick and mode;
- observed, predicted, and selected decision CPU values;
- `prediction_used`, confidence, forecast error, and parent-observed frame age;
- memory pressure, thermal proxy, and directive;
- eligible action counts and eligible/fallback worker counts;
- S1, S2, S3, S4, and geometric-mean Q;
- applied and next jitter, switching-penalty, and consensus parameters;
- controller update, step, reason, beta, saturation, and consensus-application fields;
- the sum of per-worker rejected-frame counters; and
- publisher-loop missed deadlines.

Startup diagnostics on stderr include configuration, effective random seed, signal schema, and state schema. `SCHED_FIFO` failure and environment/setup failures also use stderr, keeping diagnostics separate from CSV.

Per-worker `accepted_sequence`, heartbeat, alive state, fallback state, and rejection count exist in shared state. Of these, accepted sequence contributes to S1 signal reach, fallback state contributes to `fallback_workers`, and rejection counts are summed for CSV.

The generation-stamped transport also maintains bounded shared diagnostics for
publication attempts/successes/contention/generation exhaustion and for reader
attempts/retries/retry exhaustion/unstable slots/verification outcomes. Reader
diagnostics include bounded reason counters for HMAC, field, schema, tier,
source, directive, sequence, stale-frame, and key-epoch rejection. These are
implementation and test diagnostics; they do not add fields to the v4 CSV
contract or turn retry exhaustion into a verified frame.

The CSV metrics schemas do not currently expose per-reader retry counts, retry
exhaustion, reader-gate contention, slot/token observations, sequence-gap size,
current-frame acceptance count, controller-skip reason, key epoch, tier/source
per row, HMAC verification latency, last-known-good remaining lifetime,
fallback-reason changes, per-reader records, or a separate count of injected
tamper events. Rejections are counted only for `FRAME_INVALID`, at most once
when the invalid sequence differs from that worker's last recorded rejected
sequence. `FRAME_NO_NEW` and `FRAME_UNSTABLE` are not rejection-counter
increments.

### 2.8 Explicit limitations and future WP2 work

The current implementation establishes a concrete userspace experiment mechanism, not completion of WP2. Remaining limitations and future work include:

- no core/socket/NUMA/system hierarchy beyond the one accepted local tier value;
- no distributed clock, ordering, transport, consistency, node identity, join, leave, or partition behavior;
- no authenticated provisioning, durable root of trust, revocation, audit trail, compromise recovery, or per-source/per-tier key separation;
- every adaptive worker inherits the master and can derive every epoch key;
- no epoch-overlap, retirement, explicit sequence-wrap shutdown, or key-epoch-wrap policy;
- the fixed in-process array has no external length-validation path, and no parser/verifier fuzz campaign or schema-negotiation mechanism exists;
- no per-reader diagnostics or retry/reason counts in the paper-CPU CSV, sequence-gap telemetry, or component-level verification-latency telemetry in that CSV; bounded internal diagnostics and the separate v1 local microbenchmark protocol do not change the CSV contract;
- no long-duration generation-exhaustion/soak evidence or general publication/verification overhead budget; the v1 protocol can record bounded local invocation-level snapshot-copy and full verified-read timings, but does not establish a performance result;
- no production reclamation of a reader pin or writer lease stranded by process death; and
- no independent local-observation or conventional-scheduler fallback after signal expiry; and
- no kernel types, fixed-point encoding, kernel synchronization design, scheduler hook, or kernel selftest.

These items remain WP2/WP6/WP7/WP9 research work. A successful unit test or injected-tamper run supports only a bounded statement about that test under the tested userspace build; it is not evidence of production security, kernel suitability, distributed trust, or deployment readiness.

### 2.9 Claims

The implementation supports the statement that the current single-host userspace prototype serializes a canonical 128-byte schema-1 payload, authenticates it with a separate full HMAC-SHA256 tag, and uses the bounded generation-stamped two-slot userspace transport described in ADR 0006 before a greater-sequence frame drives a new adaptive decision.

This ADR makes no claim of kernel prototyping, kernel hot-path suitability, hard-real-time guarantees, complete WP2 validation, production key management, resistance to a compromised key-holding worker, distributed synchronization, experimentally validated security, or deployment readiness.

## 3. Alternatives Considered

### Authenticate native structure memory

Rejected because ABI padding, alignment, host endianness, and compiler behavior do not define a portable authenticated representation. The implemented field-by-field serializer removes native padding from HMAC input.

### Put the authentication tag inside the 128-byte payload

Rejected for schema 1. Keeping the 128-byte payload and separate 32-byte tag lets all state and control fields remain covered by a full HMAC without treating the tag as its own authenticated input.

### Retain the byte-wise versioned transport as the default

Rejected. The former 128 atomic payload-byte plus 32 atomic tag-byte path is
retained only behind `ORCHESTRA_SIGNAL_PUBLICATION_LEGACY` for differential
test/reference use. It is not the canonical default transport or a performance
baseline.

### Publish native structure fields as atomic words

Rejected. ADR 0006 uses twenty words only to carry the already canonical
160-byte payload-plus-tag image. It does not authenticate native C structure
memory, padding, host byte order, or floating-point fields.

### Use host-endian fields or native binary64 byte order

Rejected because artifact interpretation would depend on the producer ABI. Integers and binary64 storage bits are serialized big-endian.

### Use variable-length TLV fields, text, or JSON

Rejected for the current prototype because they introduce additional parser states and variable work. Schema 1 is fixed-size; incompatible additions require a new schema.

### Use fixed-point values

Deferred. Fixed point is expected for any kernel-oriented design because Linux kernel scheduler paths cannot use floating point. Binary64 records the current userspace experiment precisely but is not precedent for a kernel frame.

### Truncate the authentication tag

Rejected. Schema 1 retains the complete 32-byte HMAC-SHA256 output.

### Accept an authenticated frame regardless of age

Rejected because authentication does not imply freshness. A greater-sequence frame must also carry a non-future timestamp within its authenticated `max_age_ns`.

### Treat fork inheritance as production key provisioning

Rejected because possession of the shared master allows an adaptive worker to derive every epoch key, and the design has no revocation, membership, audit, or compromise-recovery protocol.

## 4. Scientific and Engineering Evidence

The paper's simulator reports detection of injected payload corruption and models stale information as reducing signal fidelity. It also identifies key distribution as unsolved and evaluates only one local coordination tier. Those simulation results motivate the mechanism but do not validate this userspace implementation or a production security property.

The current source provides byte-by-byte serializer/deserializer functions,
deterministic big-endian encoding, a full-payload HMAC, the generation-stamped
two-slot transport, bounded coherent reads, field validation, monotonic-age
validation, sequence classification, and last-known-good fallback behavior.
Focused tests cover canonical payload/HMAC vectors and frame acceptance/rejection
cases together with bounded generation-stamped publication behavior. The unit
target includes a bounded concurrent publication stress executable, and the
integration target covers shared-map protection, contention, retry exhaustion,
and stopped-process safety outcomes.

The [v1 local microbenchmark protocol](../experiments/signal_publication_microbenchmark_v1.md)
records bounded legacy/default transport invocations into a new evidence
directory when run. It preserves raw outcomes, hashes, compiler and environment
provenance, and invocation-level timing summaries for publication, successful
snapshot copying, and successful full verified reads. Its use does not turn
individual calls into independent repetitions, or local API timing into a
publication-performance, scheduler, security, or kernel result.

This remains implementation evidence, not an experimental-validation claim.
Parser fuzzing, adversarial process tests, repeated security experiments,
production crash recovery, long-duration soak, recovery-time measurement,
latency distributions, and a general overhead budget are not established by
this ADR.

## 5. Safety and Security Implications

- A greater-sequence frame does not drive a new adaptive decision unless its coherent payload passes implemented field, freshness, epoch-schedule, and HMAC checks.
- The HMAC covers all 128 payload bytes, including schema, identity, sequence, age bound, directive, predictor metadata, observed/predicted state, and controller parameters.
- The canonical 160-byte image is carried by atomic 64-bit words. A complete
  slot generation, acquired token confirmation, and a reader pin obtained from
  the separate writer-lease/reader-count gate are the coherent-snapshot
  acceptance condition; a writer refuses reuse of a pinned inactive slot.
- Future-dated and expired greater-sequence frames are invalid.
- An equal sequence is deliberately `FRAME_NO_NEW`, not a freshly authenticated acceptance or a counted rejection.
- Invalid, no-new, and unstable reads retain only the previous action while the last-known-good frame remains fresh; expiry selects the bounded userspace `THROTTLE` fallback.
- The HMAC mechanism is intended to detect accidental or injected modification while the shared master remains unknown to the modifier, but fork inheritance does not isolate the master from a compromised adaptive worker.
- No key or authentication tag is emitted in current CSV or stderr diagnostics.

These properties are scoped to source behavior. They do not constitute a threat-model closure, cryptographic certification, production-security validation, or a kernel safety case.

## 6. Performance Implications

Each committed publication serializes and authenticates the same 128-byte
payload, retains the separate 32-byte tag, writes a 20-word canonical image to
the inactive slot, and uses bounded sequence/token metadata operations. Each
snapshot attempt uses token/slot-generation checks, a reader-count pin, and up
to 20 atomic word loads; a reader makes at most ten attempts before returning
`FRAME_UNSTABLE`. ADR 0006 specifies the exact shared-operation count and
memory ordering for both the default and legacy reference transports.

For a coherent greater-sequence candidate, the reader additionally deserializes 128 bytes, validates fields and freshness, derives one epoch key, serializes the payload again for signing, computes HMAC-SHA256 over 128 bytes, and compares 32 tag bytes. Equal and lower sequences both return before freshness and HMAC verification.

The program reports publisher-loop missed deadlines. The separate v1 local
microbenchmark can record whole `publish_frame()` attempts, successful
snapshot-only copies, complete `FRAME_VALID` read/verification calls, and
retry/rejection diagnostics. It does not isolate serialization, validation,
key-derivation, or HMAC component costs; it does not provide percentiles,
cache effects, CPU isolation, end-to-end worker-loop costs, or a scheduler-time
budget. No scheduler hot-path or kernel performance conclusion follows.

## 7. Compatibility and Migration Plan

Schema 1 is the only implemented canonical userspace payload. It is byte-incompatible with the earlier native-structure authentication and with the unimplemented schema-2 layout previously described by this ADR. The earlier draft schema 2 was not a deployed compatibility contract.

Producer and adaptive consumers must run the same schema-1 implementation and
the same selected publication mode. The default is generation-stamped; the
legacy compile-time option is a separate reference/test configuration and must
not be silently mixed into a benchmark summary. A run starts with a newly
generated master, workers inherit it at `fork`, and each worker begins with
`last_sequence = 0`; there is no mixed-schema or live migration path. A
non-`1` signal schema, non-`2` state schema, nonlocal tier/source, or
inconsistent epoch is invalid.

Any field addition, field-width change, new accepted tier/source, different epoch derivation, in-band tag, different clock domain, or distributed transport requires a new schema and an ADR that defines compatibility and evidence. It must not reinterpret these 128 bytes silently.

Experiment records currently identify signal and state schema in startup diagnostics, while CSV rows use the fixed metrics header. The payload itself has no run identifier or manifest checksum. External experiment manifests and artifact provenance remain responsible for tying a run, binary, environment, and dataset together.

Switching to the legacy byte-wise reference transport requires a clean rebuild
with `ORCHESTRA_SIGNAL_PUBLICATION_LEGACY` and must be labeled as a distinct
transport configuration, not a different canonical wire protocol. Anti-replay
and key state do not persist across program restarts.

## 8. Status and Superseding ADRs

This ADR is accepted and describes the current schema-1 single-host userspace
implementation. ADR 0006 supersedes only its former byte-wise publication
subdecision. Canonical serialization, deserialization, HMAC known vectors,
byte-layout vectors, field-bound cases, sequence cases, tamper injection,
stale-frame behavior, and bounded generation-stamped publication behavior have
focused test coverage.

The decision remains classed as **Specified** because this ADR records the
contract. The implementation is a userspace prototype with bounded stress,
integration, and local-microbenchmark mechanisms, but the WP2 exit gate,
general overhead budget, long-duration/concurrent validation beyond the stated
bounds, complete key lifecycle, production fault recovery, and
security/reliability validation remain incomplete.

ADR 0006 supersedes the former byte-wise coherent-publication description only.
A future ADR must supersede this one and/or ADR 0006 if it changes the canonical
layout, authenticated byte range, tag placement or algorithm, publication
protocol, verification order, accepted identity values, sequence semantics,
freshness model, fallback behavior, or key lifecycle.
