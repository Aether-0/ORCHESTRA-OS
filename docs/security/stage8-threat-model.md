# Stage 8 — ORCHESTRA sched_ext Security Threat Model

## Local Threat Model

The ORCHESTRA sched_ext bridge operates within a single VM or machine. All BPF maps reside in kernel memory accessible only to privileged local processes. This threat model covers local threats only; network-based and remote attacks are out of scope for Stage 8.

## Threats and Mitigations

| Threat | Risk | Mitigation |
|--------|------|-----------|
| Untrusted policy file | Corrupted Q-table loaded into scheduler | SHA-256 digest validation, strict dimension checks, non-finite rejection |
| Malicious bridge arguments | Shell injection, path traversal | Fixed-width integer parsing, no shell execution, explicit --target-pid validation |
| PID reuse | Stale directive targets wrong task | TGID + PID + start-time cookie, short expiry (30s), task-exit cleanup |
| Map tampering | Direct BPF map modification by root | Maps pinned under restricted /sys/fs/bpf paths; map schema validation on every read |
| Stale pinned maps | Old scheduler maps left after crash | Explicit cleanup on load; generation sentinel at zero prevents stale reads |
| Privilege misuse | Unintended capability escalation | CAP_BPF + CAP_SYS_ADMIN required for load; bridge operates on already-loaded maps with minimal perms |
| Integer overflow | Generation or size overflow | Checked arithmetic on all counter increments; UINT64_C macros; compile-time size assertions |
| Kernel version mismatch | Build-time vs runtime API mismatch | Schema version in bridge control map; version mismatch → safe RUN fallback |
| Malicious guest output | Prompt injection via kernel logs | All guest output treated as untrusted; no command construction from logs |

## Hardening Checklist

- [x] Bridge CLI validates all integer inputs
- [x] Policy SHA-256 validated before map population
- [x] Two-slot publication prevents partial generation exposure
- [x] Task identity uses TGID + PID + cookie
- [x] Directive expiry enforced (30s default)
- [x] Map schema validated on every bridge read
- [x] Generation overflow produces stable exit code (10)
- [x] Invalid PID produces stable exit code (6)
- [x] BPF dispatch bounded (no unbounded loops)
- [ ] Privilege drop after scheduler attach (pending capset implementation)
- [ ] Symlink-safe temporary file handling (pending O_NOFOLLOW)
- [ ] World-readable map prevention (pending umask enforcement)
