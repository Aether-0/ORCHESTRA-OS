# Preserved harness failure

- Timestamp: 2026-08-21T11:25Z (local campaign execution window)
- Scope: first combined canonical-action harness attempt
- Cause: the campaign `actions/` directory was absent, and the shell template passed literal `${action}` paths.
- Effect: workers ran under the loaded scheduler, but every bridge/status/map capture failed before publication; no action verdict is derived from this attempt.
- Recovery: rerun uses the existing bridge and workload with a created result directory; implementation files were not changed.
