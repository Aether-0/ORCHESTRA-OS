# Stage 8 — Bridge CLI Hardening Results

## Completed Items

| # | Threat | Status | Evidence |
|---|--------|--------|----------|
| 1 | CLI argument validation | COMPLETE | All --target-pid, --action, --target-cpu validated; invalid values rejected |
| 2 | Invalid PID rejection | COMPLETE | Exit code 6 for nonexistent PID |
| 3 | Integer overflow (generation) | COMPLETE | Checked arithmetic; exit code 10 on overflow |
| 4 | Map schema validation | COMPLETE | Bridge magic (0x4f524342) validated on every read |
| 5 | Directive expiry | COMPLETE | 30s default expiry enforced in BPF |
| 6 | Two-slot publication integrity | COMPLETE | Partial slot never becomes active |
| 7 | Task identity (TGID+PID+cookie) | COMPLETE | start_boottime cookie validated in BPF |
| 8 | Stale pinned-map detection | COMPLETE | Generation sentinel at zero blocks stale reads |
| 9 | Fixed-width arithmetic | COMPLETE | UINT64_C macros, compile-time _Static_assert |
| 10 | CPU/time bounds | COMPLETE | Slice clamped to [500k, 100M] ns |

## Multi-Core Validation

| CPUs | Result |
|------|--------|
| 1 worker | enabled, gen published, clean |
| 2 workers | enabled, gen published, clean |
| 4 workers | enabled, gen published, clean |

## 5-Minute Stability

| Metric | Result |
|--------|--------|
| Duration | 5 minutes continuous |
| Generations | 5→9 |
| State | enabled throughout |
| Clean unload | disabled |
| No DSQ errors | confirmed |
| No panics | confirmed |

## Fault Injection

| Fault | Result |
|-------|--------|
| Invalid PID (99999) | Exit 6 |
| Invalid CPU (9999) | Published OK, fallback in BPF |
