# 10. Signal Bus

## Design

The ORCHESTRA Signal Bus is a C11 atomic multi-reader, single-writer shared memory transport for versioned, cryptographically protected scheduling signal frames.

## Frame Format

```
Offset  Size  Field
0       4     magic (0x4f524348 = "ORCH")
4       4     schema_version (1)
8       4     tier (1 = core-local)
12      4     source_id (0 = local)
16      8     sequence (monotonic)
24      8     monotonic_ns
32      8     max_age_ns
40      4     key_epoch
44      4     directive (action enum)
48      4     state_schema_version
52      4     prediction_used
56      8     cpu_now (binary64)
64      8     cpu_pred
72      8     decision_cpu
80      8     memory_pressure
88      8     thermal_proxy
96      8     confidence
104     8     jitter_sigma
112     8     switch_penalty
120     8     consensus_blend
──────────────────────
128    32    HMAC-SHA256 tag
```

Total: 160 bytes. Big-endian wire format. No native struct serialization.

## Publication Protocol

### Writer (Publisher)
1. Load current `publication_token`
2. Compute inactive slot: `1 - (token & SLOT_MASK)`
3. Acquire writer lock on inactive slot (bit 63 of access_state)
4. Write odd slot sequence (generation | 1)
5. Store 20 atomic 64-bit frame words
6. Write even slot sequence (generation) — release ordering
7. Write publication_token (generation | slot) — release ordering
8. Release writer lock

### Reader (Worker)
1. Acquire-load publication_token
2. Determine active slot and expected generation
3. Pin as reader on that slot (increment access_state)
4. Verify token hasn't changed
5. Acquire-load slot sequence
6. Reject if sequence is odd or doesn't match generation
7. Load 20 atomic 64-bit frame words
8. Acquire-load slot sequence again
9. Acquire-load publication_token again
10. Accept only if both sequences match, both tokens match, sequence is even
11. Unpin reader

### Fallback
- Max 10 retries
- Retry exhaustion → use last-known-good frame or safe fallback
- HMAC/Schema/Sequence/Tier/Source/Epoch/Directive validation on accepted frame

## Key Properties
- **No torn reads:** Odd sequence prevents acceptance during write
- **No ABA:** Generation in sequence prevents slot reuse confusion
- **No data races:** All shared memory accessed atomically
- **Bounded reader:** Fixed retry limit, no unbounded spin
