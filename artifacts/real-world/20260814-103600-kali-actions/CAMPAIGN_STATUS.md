# Action campaign after 7.0 port (20260814-103600)

Scheduler: loaded `orchestra_scx_stage7` (API 70012), stayed enabled, unloaded clean (`unregistered from user space`). No new DSQ 0x0 abort.

## Fixes this session
- Bridge `--status` now prints enqueue, run/yield/migrate/throttle/sleep, deferred, stale_lease, bad_id, expired, bad_cpu, map_err.
- Action workers changed from pure spin (may not re-enqueue) to `sleep 0.01` loops.

## Results (one loaded session, then a second with extended telemetry)

| Action | Published | Effective? | Evidence |
|---|---|---|---|
| Load/unload | n/a | **PASS** | state enabled→disabled, dmesg unregister |
| RUN | gen=1 | **INCONCLUSIVE** | accepted 0; run_disp rises for whole system (full switch fallback RUN) |
| YIELD | gen=2 | **INCONCLUSIVE** | accepted +1; yield_disp 0 then 1 later — not a clear per-task yield |
| SLEEP | gen=3, 2s not-before | **not effective as observed** | sleep_acc=0 sleep_def=0 deferred=0 |
| THROTTLE | gen=4 | **weak** | throttle_acc=1 after later window; throttle_def=0 |
| MIGRATE to CPU 3 | gen=5 | **not effective** | PSR stayed 0 (taskset -c 0); mig_acc=0 mig_disp=0 migrate_target=0 |
| 4 workers × 8s | RUN | **full-switch owned** | 7997ms, ctx_delta=231675; not isolated opt-in |

Fallback ≈ running for the whole machine (no directive on most tasks). `bad_id=0 stale_lease=0 expired=0 map_err=0`.

Per-task `task identity=` lines never appeared: telemetry hash is only filled after a matched directive in `place_with_snapshot`.

## Diagnosis
Directives are stored (status lists them) but almost never match at enqueue (`accepted` rises by ~1 per publish, not per wakeup). Likely BPF `task_identity(p)` vs userspace map key, or `load_directive` failing the coherent snapshot without a dedicated counter. Not a DSQ-0 crash.

## Claim
`KERNEL_PROTOTYPED` on this host for **attach, full-switch running, clean unload**. Canonical actions **requested**, not **effective**, except possible single YIELD/THROTTLE hits.

IMPLEMENTATION: wrapper port + status telemetry. No 6.12 kernel install (NVMe).
