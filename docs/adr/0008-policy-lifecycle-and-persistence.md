# Policy Lifecycle and Persistence

Status: **Implemented**

## Motivation

The ORCHESTRA-OS userspace prototype previously operated in a single mode where policy learning, adaptation, and controller feedback were continuously active. This inhibited:
1. Reproducible evaluation: no way to freeze a policy and replay it identically.
2. Safe adaptation: no distinction between aggressive exploration (training) and conservative tuning (adaptation).
3. Policy portability: no serialized policy format for cross-run reuse.

This ADR defines a policy lifecycle with three explicit modes (TRAIN, ADAPT, EVALUATE), a canonical binary policy file format, deterministic save/load, and controller-state gating.

## TRAIN mode

- Exploration enabled (epsilon-greedy with the declared schedule).
- Q-table updates enabled when controller state permits.
- Difference-reward updates applied.
- Consensus learning enabled.
- Policy generation increments on each applied controller update.

## ADAPT mode

- Exploration disabled (greedy selection only).
- Q-table updates enabled only in NORMAL state; suppressed in DEGRADED, SATURATED, ROLLBACK, DISABLED.
- Consensus learning enabled.
- Policy generation increments on each applied update.

## EVALUATE mode

- Exploration disabled.
- Q-table updates suppressed unconditionally.
- Consensus learning suppressed.
- Policy generation frozen.
- For identical policy file, seed, and configuration, policy decisions are reproducible.

## Controller-state gating matrix

| Policy Mode | NORMAL | DEGRADED | SATURATED | ROLLBACK | RECOVERY | DISABLED |
|------------|--------|----------|-----------|----------|----------|----------|
| TRAIN      | updates | updates | suppressed | suppressed | suppressed | suppressed |
| ADAPT      | updates | suppressed | suppressed | suppressed | suppressed | suppressed |
| EVALUATE   | suppressed | suppressed | suppressed | suppressed | suppressed | suppressed |

Invalid, stale, unauthenticated, or unstable frames never update Q values regardless of mode.

## Canonical policy-file format

Fixed binary encoding with big-endian wire format:

| Offset | Size | Field |
|--------|------|-------|
| 0 | 4 | magic (0x504f4c59 = "POLY") |
| 4 | 4 | format version (1) |
| 8 | 4 | schema version (1) |
| 12 | 4 | header length (64) |
| 16 | 4 | payload length |
| 20 | 4 | state count |
| 24 | 4 | action count |
| 28 | 8 | policy generation |
| 36 | 8 | training update count |
| 44 | 8 | adaptation update count |
| 52 | 12 | padding |
| 64 | N | Q-table payload (state_count * action_count * 8 bytes) |
| 64+N | 32 | SHA-256 digest of payload |

No pointers, no ABI padding, no floating-point NaN/Inf. Strict validation rejects truncated, oversized, non-finite, and digest-mismatched files.

## Atomic save procedure

1. Serialize to a temporary file (`.tmp.<pid>`).
2. Flush and close.
3. Reopen and validate the temporary file.
4. Rename atomically over the destination.
5. On failure, remove temporary and preserve previous policy.

## Load-failure behavior

When an explicitly requested policy file fails to load: return nonzero status, emit a stable error code, do not silently continue with random or uninitialized policy.

When no policy input is requested: use the standard deterministic Q-table initialization (all zeros).

## Metrics v6 strategy

An append-only `orchestra.paper_cpu.metrics/v6` schema adds 13 policy-telemetry columns to the strict 107-column v5 contract, yielding 120 columns. New fields: policy_mode, policy_schema_version, policy_generation, policy_update_allowed, policy_update_applied, policy_update_suppression_reason, policy_exploration_enabled, policy_train_update_count, policy_adapt_update_count, policy_load_status, policy_save_status, policy_digest_prefix, policy_format_version.

## Computational complexity

Save/load: O(QTABLE_SIZE) per operation. Hot path: O(1) atomic loads for gating decisions.

## Local threat model

The SHA-256 digest provides corruption detection only. No cryptographic authentication. An attacker with local write access can replace the policy file. The format is designed for research reproducibility, not adversarial security.

## Limitations

- Policy files are not authenticated.
- No migration between policy schema versions.
- No incremental policy export.
- Policy telemetry delayed by one controller cadence.
