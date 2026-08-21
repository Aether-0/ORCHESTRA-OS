# Executive summary

Campaign ID: `20260821-111936-kali-continuation`  
Date: 2026-08-21  
Host: `kali`  
ORCHESTRA revision: `82f69cbac2d9bf4ffa1372550f73d9c2c084b8f9`  
Kernel: `7.0.12+kali-amd64`  
sched_ext: available; final state disabled  
Overall result: `PARTIALLY_VALIDATED`

Checklist:

- Applicable: 519
- PASS: 94
- FAIL: 0 checklist items
- BLOCKED: 386 (208 are `BLOCKED_NOT_IMPLEMENTED`)
- INCONCLUSIVE: 39
- N/A: 0

Validated on this machine:

- Userspace build and regression gates.
- Kernel capability/BTF/BPF gates.
- Fresh stage7 BPF build, load, repeated unload, and final cleanup.
- Exact-TID ownership in a controlled positive RUN trial.
- RUN, YIELD, MIGRATE, and budgeted THROTTLE telemetry.
- SLEEP deadline suppression and release telemetry, with a lifecycle limitation.
- CFS baseline matrix and fault-input rejection.

Critical findings:

- None. No panic, lockup, data loss, thermal safety event, or unload failure occurred.

High findings:

- The matched ORCHESTRA comparison passed the all-target ownership gate in only 2 of 9 rows. The timing inflation is therefore not a valid ORCHESTRA performance result.

Not validated:

- Kernel predictive signal bus, predictor, S1/S2/S3/S4/Q, feedback controller, full RT safety layer, NUMA-aware policy, distributed tier, valid ORCHESTRA stress comparison, and portable CFS/scx_simple/perf comparison.

Most important reason for current limitations:

- The checkout contains a stage7 kernel scheduler prototype and userspace research components, not the full architecture required by the 519-item acceptance checklist. The available comparison/stress scripts also lack portable, ownership-validating execution and the host has one NUMA node.

Recommended next action:

- Treat this checkout as kernel-prototyped/partially validated. Before another acceptance campaign, implement and expose the missing kernel layers, establish a stable exact-TID ownership gate, and provide a bounded portable benchmark/stress harness. No implementation changes were made in this campaign.
