# ADR 0006: Generation-stamped signal publication

- Status: Accepted - implemented in the current userspace prototype
- Date: 2026-08-04
- Decision class: Implementation transport decision
- Implementation status: Single writer/multiple reader bounded userspace transport; focused stress, integration, and local-microbenchmark harnesses exist, but WP2 validation is incomplete
- Maturity scope: Single-host userspace prototype only
- Work package: WP2 Signal Bus and Kernel Communication Infrastructure
- Related: ADR 0002, Userspace Canonical Signal Frame and Verification Contract
- Supersedes: ADR 0002 section 2.4's former versioned atomic-byte publication transport only
- Superseded by: None

## 1. Context

ADR 0002 fixes the schema-1 signal contract: a canonical 128-byte payload and
a separate 32-byte HMAC-SHA256 tag. Its former shared-memory transport used
160 individual atomic byte cells guarded by a publication-version seqlock. That
transport remains valuable as a reference, but its byte-wise copying is no
longer the default implementation.

The userspace prototype needs one parent writer and multiple adaptive-worker
readers to obtain one coherent canonical payload-plus-tag image. The transport
must retain canonical serialization, HMAC coverage, freshness, sequence,
schema, tier, source, and key-epoch checks. It must not allow a reader to
accept a torn image, overwrite a reader-pinned slot, wait without a bound, or
reuse a generation token after exhaustion.

This decision is deliberately transport-scoped. Linux remains the scheduler.
It makes no kernel integration, sched_ext, scheduler-hot-path, hard-real-time,
security-certification, or publication-performance claim.

## 2. Decision

### 2.1 Canonical image and fixed shared layout

The authenticated wire contract is unchanged. The publisher first constructs:

~~~text
canonical image = canonical_payload[128] || hmac_sha256_tag[32]
image bytes      = 160
image words      = 20 atomic uint64 words
~~~

The twenty words carry contiguous eight-byte chunks of the canonical byte
image. They do not carry native C structure fields, padding, host byte order,
or an alternate HMAC input. The reader reconstructs the same canonical bytes
before deserialization and verification.

The canonical signal-bus mapping contains two fixed slots. Each slot has:

- a 20-word atomic canonical image;
- an atomic slot sequence; and
- no reader-mutated payload, HMAC, key, policy, or scheduler state.

A separate companion MAP_SHARED reader-gate mapping has exactly one atomic
access_state for each slot. The high bit is a writer-exclusive lease and the
remaining low bits are a reader-pin count. The gate map contains no canonical
payload bytes, HMAC tag, key, policy, or scheduler data. Workers keep the
canonical token/slot/payload bus mprotect(PROT_READ); only the two gate entries
are writable for reader pinning.

C11 does not itself define the behavior of C atomic objects shared between
processes. This implementation is therefore scoped to the Linux/POSIX target
where related processes use these `MAP_SHARED | MAP_ANONYMOUS` mappings and the
selected atomic objects are lock-free. Before workers start, the program checks
the required selected publication and gate atomic objects and representative
shared-control atomic types with `atomic_is_lock_free`; failure terminates the
run rather than selecting a non-atomic fallback. That is a platform assumption
checked at runtime, not an ISO C inter-process portability proof.

### 2.2 Token, generation, and slot-state encoding

The single publication token is:

~~~text
token = (generation << 1) | active_slot
~~~

active_slot is 0 or 1. Token zero means no committed frame has been
published. Generations begin at 1 and are bounded by UINT64_MAX >> 1. The
implementation refuses further publication when it cannot advance without
generation reuse. It does not wrap, reinterpret, or silently reset a token.

For a slot assigned generation g:

~~~text
slot sequence = (g << 1)       complete
slot sequence = (g << 1) | 1   writer in progress
~~~

A completed reader snapshot must match the selected token's generation and
the even complete slot sequence. Token zero, an odd sequence, a different
generation, or any failed confirmation is not an accepted frame.

### 2.3 Writer ownership and publication

The parent is the sole publisher. It serializes/signs in process-local buffers
before attempting a slot lease. For tamper injection, it retains the normal
tag while replacing the selected canonical payload bytes exactly as ADR 0002
defines; the frame remains coherent but fails HMAC verification.

For a new generation the writer:

1. acquires the current token with acquire ordering and selects the inactive slot;
2. obtains that slot's high-bit writer lease only if its low-bit reader count is zero;
3. marks the chosen slot sequence in progress;
4. writes all twenty canonical-image words;
5. releases the matching even complete slot sequence;
6. releases the new generation/active-slot token; and
7. releases the writer lease.

The writer gate acquisition is an atomic ownership transition, not a load-then-
store observation. It closes the race between a writer's zero-reader check and
a reader's attempt to pin the slot. If it cannot acquire the inactive-slot
lease in its single bounded ownership attempt, it refuses publication.
It does not block, spin indefinitely, overwrite a pinned slot, publish a
partial image, or weaken authentication/freshness validation. An exhausted
generation likewise refuses publication safely.

The successful writer ordering is explicit. It loads the current token with
acquire ordering; the writer-lease compare/exchange is acquire-release on
success and acquire on failure; it stores the odd sequence with release
ordering; it stores the twenty image words relaxed; it stores the matching even
sequence with release ordering; it stores the new token with release ordering;
and it clears the gate with a release store. The release token is the
publication edge for the completed image; the gate protects reuse while a
reader owns a pin.

### 2.4 Reader pinning and bounded coherent snapshot

Each reader attempts at most ten snapshots. One attempt:

1. acquires the publication token and rejects token zero as no committed frame;
2. derives the active slot and generation from that token;
3. obtains a low-bit reader pin only if the gate high-bit writer lease is clear;
4. re-acquires and confirms the same token after pinning;
5. acquires and confirms the matching even slot sequence, then copies all twenty words while pinned;
6. re-acquires and confirms both token and slot sequence; and
7. releases its pin before either accepting the copy or retrying.

A failed pin, token confirmation, slot-sequence confirmation, or generation
confirmation causes release of any acquired pin and a bounded retry. Acquire
loads observe the completed slot/token publication; release stores publish the
complete slot/token and make pin removal visible to a waiting-free writer.
The gate lease prevents the selected slot from being reused during the copy.
Therefore readers never accept an in-progress or torn canonical image.

The reader-pin compare/exchange itself has at most four attempts before that
snapshot attempt fails. This smaller bound is nested inside, not in addition
to, the ten-attempt snapshot bound.

For a successful generation-stamped snapshot attempt, the reader uses an
acquire token load; an acquire gate load followed by at most four weak
compare/exchanges (acquire-release on success and acquire on failure); an
acquire token recheck; an acquire slot-sequence load; twenty relaxed word
loads; final acquire sequence and token loads; and a release pin decrement.
Some failed attempts perform a strict subset of those operations. The fixed
limit is ten snapshot attempts, so there is no unbounded retry path.

`unstable_slot_observations` is a transport diagnostic, not a count of accepted
bad frames. In the generation-stamped path it records a failed pin/generation
check, post-pin token mismatch, sequence mismatch, or final token/sequence
confirmation mismatch. In the legacy reference it also records a failed final
version confirmation. Every such observation retries or returns
`FRAME_UNSTABLE`; it cannot become `FRAME_VALID` without the normal subsequent
validation and HMAC acceptance path.

After ten failed attempts, the reader reports FRAME_UNSTABLE. Retry exhaustion
does not create a new adaptive decision, reward update, consensus action,
controller update, or effective-action success. It follows the existing
last-known-good and bounded userspace fallback contract.

### 2.5 Legacy reference transport

ORCHESTRA_SIGNAL_PUBLICATION_LEGACY selects the former byte-wise atomic
versioned transport at compile time. It remains for differential tests and
reference comparisons while the generation-stamped path is validated. Both
modes preserve the same canonical serialization, payload schema, HMAC,
verification order, freshness, and sequence semantics. The option is not a
runtime negotiation mechanism, a production fallback, or a performance
baseline. A clean rebuild is required to change it.

## 3. Alternatives Considered

### Retain byte-wise publication as the default

Rejected. It remains a narrow compile-time reference, but the default now
uses a fixed twenty-word image and two-slot ownership protocol.

### Use a plain double buffer with no reader ownership

Rejected. A writer could begin reusing the formerly active slot while a reader
still copied it. The gate lease and reader pins make that ownership explicit.

### Block until the inactive slot becomes available

Rejected. A bounded userspace publication path must refuse contention rather
than wait indefinitely or silently exceed its timing contract.

### Use dynamic allocation, hazard pointers, or unbounded RCU retirement

Rejected. The transport has exactly two slots, two gate entries, fixed word
count, and bounded retries. No dynamic allocation occurs in publication or
snapshot paths.

### Change the authenticated serialization to native 64-bit words

Rejected. Atomic words are a transport representation only. Canonical
big-endian byte serialization remains the sole HMAC and parser contract.

## 4. Scientific and Engineering Evidence

Focused source tests and deterministic publication hooks cover canonical image
reconstruction, token and slot-state bounds, retry exhaustion, writer
contention refusal, reader pinning, generation exhaustion behavior, and
legacy-reference equivalence. The standard unit target also runs a bounded
high-frequency concurrent publisher/four-reader stress executable; the
integration target exercises read-only shared mappings, contention, retry
exhaustion, and intentionally stopped reader/publisher cases. They support
bounded source behavior under their stated build and host conditions.

The separately documented [v1 local microbenchmark protocol](../experiments/signal_publication_microbenchmark_v1.md)
compiles both transport modes, preserves all invocation artifacts and
provenance, and records bounded local publication, successful snapshot-copy,
and successful full-verified-read timings when it is run into a new evidence
directory. Its statistical unit is one completed bounded invocation, not an
individual reader call. A legacy reference rejection is preserved with its
reason; a generation-stamped non-tampered invocation requires no such
rejection to be included. This is bounded local implementation evidence, not a
general no-torn-frame proof outside the tested interleavings or a performance
result.

Neither the tests, a microbenchmark run, nor this ADR establishes publication
latency distributions, cache behavior, scalability across sockets/NUMA/nodes,
production key-management safety, adversarial-process resistance, scheduler
performance, or kernel suitability. Long-duration generation-exhaustion and
contention-soak evidence remains future work.

## 5. Safety and Security Implications

- Canonical payload bytes and the separate full HMAC remain unchanged and are
  still verified after a coherent snapshot.
- In the normal prototype reader path, a reader operation mutates only its gate
  pin count; the canonical payload, tag, token, and slot sequence remain in
  the read-only bus mapping. This is not a defense against a compromised
  key-holding worker or a production shared-memory access-control claim.
- The writer takes exclusive ownership of the inactive slot before changing
  its in-progress sequence or words, and refuses reuse while any reader pin exists.
- Token, slot sequence, and generation checks reject incomplete or stale
  transport state before it reaches normal frame validation.
- Generation exhaustion and bounded contention fail closed for publication:
  no torn or partially authenticated frame becomes accepted.
- A reader or publisher that dies while holding a gate pin or writer lease can
  leave that gate permanently nonzero. The implementation treats this as an
  availability loss: later publication refuses bounded contention and readers
  retain last-known-good state or use the existing bounded fallback. There is
  no production lease reclamation. The integration test's explicit gate reset
  is test-only cleanup, not crash recovery.
- Existing invalid/stale frame rules and last-known-good fallback remain
  responsible for operational continuity; this transport does not make Linux
  hand off or regain scheduler control.

## 6. Performance Implications

The shared-operation count is fixed and auditable, but it is not a cycle-cost
model. A successful legacy reference publication performs one acquire version
load, two version read-modify-writes (the first acquire-release to mark odd,
the final release to mark even), and 160 relaxed atomic byte stores. A
successful generation-stamped publication performs one acquire token load, one
strong writer-gate compare/exchange, one release odd-sequence store, twenty relaxed
atomic 64-bit word stores, one release even-sequence store, one release token
store, and one release gate-unlock store. Local packing of the 160 canonical
bytes into twenty words is not a shared atomic transport operation.

For the generation-stamped reader, at most ten snapshot attempts each use the
bounded gate/token/sequence protocol stated above; a successful attempt copies
twenty relaxed words while pinned. For the legacy reader, an attempt uses two
acquire version loads, 160 relaxed byte loads, and an acquire fence before the
final version comparison, again with at most ten attempts. These counts exclude
the subsequent deserialization and authentication path and do not predict
cache, CPU, or elapsed-time cost.

The v1 local microbenchmark records invocation-level publication timing,
successful snapshot-copy timing, complete `FRAME_VALID` verified-read timing,
and retry/rejection diagnostics under explicitly recorded compiler, host,
warm-up, contention, and repetition controls. It is descriptive and unpaired;
it does not provide tail distributions, a general overhead budget, a scheduler
hot-path budget, or a claim that either path is faster in a broader workload.

## 7. Compatibility and Migration Plan

Schema-1 payload bytes, tag placement, HMAC algorithm, key derivation, frame
verification order, freshness checks, and action semantics are unchanged.
The generation-stamped mechanism is an implementation-internal shared-memory
transport revision, not a new signal schema or metrics schema.

Existing v2/v3/v4 CSV evidence remains historical and must not be rewritten or
silently pooled with a future publication-transport comparison. Experiment
metadata must record the binary/source hash and whether the default or legacy
compile-time path was used. A legacy build and a default build are distinct
transport configurations, even though their canonical frame bytes are the same.

Rollback is a clean rebuild with ORCHESTRA_SIGNAL_PUBLICATION_LEGACY. It is
permitted only as a test/reference configuration and does not relax frame
verification or justify mixing results.

## 8. Status and Future Work

This ADR is accepted for the current single-host userspace prototype and
supersedes only ADR 0002's old byte-wise publication transport description.
It does not complete WP2. Bounded stress, integration, and local timing
protocols exist, but remaining work includes general publication and
verification budgets, long-duration soak/wrap testing, parser fuzzing, fault
injection beyond the current bounds, production crash/lease recovery, key
lifecycle design, hierarchical tiers, distributed ordering, kernel
synchronization design, and kernel selftests.

A future change to word packing, token encoding, gate ownership, retry bound,
generation exhaustion behavior, mapping protection, canonical payload/tag
layout, or verification order requires an ADR and test review. No claim in
this ADR constitutes kernel integration, hard-real-time behavior, deployment
readiness, or causal scheduler-performance improvement.
