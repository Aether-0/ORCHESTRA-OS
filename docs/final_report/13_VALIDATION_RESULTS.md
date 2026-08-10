# 13. Validation Results

## Test Suite Summary

| Category | Count | Compiler | Result |
|----------|-------|----------|--------|
| Unit tests | 25 | GCC + Clang | 25/25 |
| CSV validator | 34 | Python 3 | 34/34 |
| Benchmark runner | 21 | Python 3 | 21/21 |
| Integration | 5 | GCC + Clang | 5/5 |
| Publication stress | 10,000+ | GCC + Clang | 0 torn frames |
| Clang static analysis | 1 pass | Clang 18.1.8 | 0 findings |
| ASan | full suite | GCC | 0 findings |
| UBSan | full suite | GCC | 0 findings |

## Kernel Runtime Validation

| Gate | Stage | Result |
|------|-------|--------|
| scx_simple 3-cycle | 6B, 7, 8 | PASS |
| ORCHESTRA BPF verifier | 6B, 7, 8 | PASS |
| struct_ops attach | 6B, 7, 8 | PASS |
| state=enabled | 6B, 7, 8 | PASS |
| Bridge status (magic 0x4f524342) | 7, 8 | PASS |
| 5 load/unload cycles | 6B, 7, 8 | PASS |
| Publish gen 1→6 | 7, 8 | PASS |
| Invalid PID (exit 6) | 7, 8 | PASS |
| Invalid CPU fallback | 7, 8 | PASS |
| 5-min stability | 8 | PASS |
| Clean disable | ALL | PASS |

## Controller Gating

| State × Action | RUN | YIELD | MIGRATE | THROTTLE | SLEEP |
|---------------|-----|-------|---------|----------|-------|
| NORMAL | ✓ | ✓ | ✓ | ✓ | ✓ |
| DEGRADED | ✓ | ✓ | ✗ | ✓ | ✗ |
| SATURATED | ✓ | ✗ | ✗ | ✗ | ✗ |
| ROLLBACK | LKG | ✗ | ✗ | ✗ | ✗ |
| RECOVERY | ✓ | ✓ | ✗ | ✗ | ✗ |
| DISABLED | RUN only | ✗ | ✗ | ✗ | ✗ |

## Error-Free Properties

| Property | Campaigns | Errors |
|----------|-----------|--------|
| Invalid DSQ | 20+ | 0 |
| Kernel panic | 20+ | 0 |
| Kernel BUG | 20+ | 0 |
| Scheduler stall | 20+ | 0 |
| Stranded task | 20+ | 0 |
| Partial generation | 10+ | 0 |
| Torn frame | 10,000+ | 0 |
| HMAC failure (valid) | ALL | 0 |
| Clang analyzer | ALL | 0 |
