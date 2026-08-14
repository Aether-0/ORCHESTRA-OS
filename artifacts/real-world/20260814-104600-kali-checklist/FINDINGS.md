# Findings (consolidated, severity order)

IMPLEMENTATION MODIFIED: YES for F6 mitigation (operator-authorized 7.0 wrappers). NO for userspace tests, CFS baselines, or action semantics.

---

FINDING ID: F7
TITLE: First 7.0 attach used DSQ id 0 and aborted (ksoftirqd/22)
SEVERITY: HIGH
TEST ID: T-load-dsq0
STATUS: FAIL then mitigated (later loads PASS)

OBSERVATION:
After wrapping dispatch→dsq_insert, the first `orchestra_loader --load` enabled then disabled with runtime error `non-existent DSQ 0x0 for ksoftirqd/22`. Subsequent rebuild with `#undef` of zeroed `SCX_DSQ_*` / `SCX_KICK_IDLE` / `SCX_ENQ_HEAD` from `enums.autogen.bpf.h` stayed enabled.

EXPECTED:
Loaded scheduler remains enabled until user-space unregister.

EVIDENCE:
- `artifacts/real-world/20260814-102000-kali-7port/sched_ext/dmesg_scx.txt`
- Later dmesg: `disabled (unregistered from user space)` only
- `20260814-104600-kali-checklist/sched_ext/dmesg.txt` still contains the first abort plus later clean unregisters

REPRODUCIBILITY:
1/1 without enum restore; 3/3 load cycles + action session + RT session stayed enabled with restore.

FIRST FAILURE POINT:
DSQ constants were 0 because generic loader does not inject `SCX_OPS_LOAD` skeleton volatiles.

LIKELY COMPONENT: BPF / loader / sched_ext DSQ IDs

MOST LIKELY CAUSE:
Zeroed autogen enums, not a bad kfunc name after the insert port.

ALTERNATIVE CAUSES:
Wrong object; timer map missing. Less likely after pin-before-attach loader succeeded on retry.

EVIDENCE AGAINST ALTERNATIVES:
Same object path after undef rebuild; maps pinned; state=enabled.

CONFIDENCE: HIGH

IMPACT: Safety/correctness of attach. Unmodified 7.0 compile-without-undef is unsafe.

RECOMMENDATION:
Keep enum restore or inject correct DSQ values in the loader. Do not use bare `bpftool struct_ops register` for this object.

IMPLEMENTATION MODIFIED: YES (enum undef). Action algorithms unchanged.

---

FINDING ID: F8
TITLE: Canonical action publish does not prove effective per-task scheduling
SEVERITY: HIGH
TEST ID: T-actions
STATUS: FAIL (MIGRATE, SLEEP effectiveness); INCONCLUSIVE (RUN, YIELD, THROTTLE)

OBSERVATION:
While `orchestra_scx_stage7` was enabled (`switch_all=1`), bridge `--publish` stored directives (status listed generation and action). `accepted` typically rose by ~1 per publish, not per wakeup. `sleep_acc=0 sleep_def=0 deferred=0`. MIGRATE worker stayed on CPU 0 under `taskset -c 0` with target CPU 3; `mig_acc=0 mig_disp=0 migrate_target=0`. Per-task `task identity=` lines never printed. `bad_id=0 stale_lease=0 expired=0 map_err=0`. System-wide `running` and `fallback` were both large (fallback ≈ running).

EXPECTED:
For an admitted TID, enqueue should match the published identity, increment accepted/dispatched meaningfully, and MIGRATE should change observed CPU when the target is online and affinity allows.

EVIDENCE:
- `20260814-103600-kali-actions/actions/*_status.txt`
- `20260814-103600-kali-actions/CAMPAIGN_STATUS.md`
- `20260814-102000-kali-7port/ownership/*`

REPRODUCIBILITY:
1 loaded action session with extended telemetry; exploratory n=1 earlier. Not a 5-run statistical claim.

FIRST FAILURE POINT:
Directive map lookup / coherent snapshot at enqueue (`place_with_snapshot` / `task_identity`), not load failure.

LIKELY COMPONENT: action implementation / identity keying / instrumentation

MOST LIKELY CAUSE:
Userspace map key does not match BPF `task_identity(p)`, or snapshot load fails without a dedicated counter.

ALTERNATIVE CAUSES:
Workers not re-enqueued (mitigated by sleep-loop workers); affinity blocking MIGRATE (taskset -c 0 would block CPU 3 — that alone can explain no CPU movement even if migrate were accepted; but mig_acc stayed 0, so request was not accepted). SLEEP not-before window.

EVIDENCE AGAINST ALTERNATIVES:
Affinity explains missing CPU move only if migrate was accepted; counters show it was not. SLEEP counters never incremented.

CONFIDENCE: HIGH that effectiveness is unproven; MEDIUM on exact identity mismatch.

IMPACT: Claim scope. Kernel remains KERNEL_PROTOTYPED for attach/full-switch, not EXPERIMENTALLY_VALIDATED for the canonical action set.

RECOMMENDATION:
Trace identity bytes on both sides; add/observe a snapshot-fail counter if one exists in source; do not treat `accepted+1` as action success.

IMPLEMENTATION MODIFIED: NO for action logic (status print only).

---

FINDING ID: F6
TITLE: Unmodified Stage-7 BPF cannot load on Linux 7.0.12 (missing scx_bpf_dispatch)
SEVERITY: HIGH
TEST ID: T-load-register
STATUS: FAIL (historical); mitigated by authorized 7.0 port

OBSERVATION:
Compile vs 7.0 `common.bpf.h`: undeclared `scx_bpf_dispatch`. Compile vs 6.12 headers + 7.0 vmlinux.h: object built. `bpftool struct_ops register`: `scx_bpf_dispatch: not found in kernel or module BTFs`. Kernel BTF has `scx_bpf_dsq_insert*`.

EXPECTED:
Object kfuncs exist in running BTF.

EVIDENCE:
`20260814-095200-kali-auth/sched_ext/register.stderr`, `build/bpf_stage7b.stderr`, `build/bpf_612b.stderr`, `sched_ext/scx_kfuncs.txt`

REPRODUCIBILITY: 1/1 before port.

FIRST FAILURE POINT: ksym resolution of `scx_bpf_dispatch`.

LIKELY COMPONENT: Kernel / sched_ext API version

MOST LIKELY CAUSE: Upstream rename after 6.12.

ALTERNATIVE CAUSES: Wrong object. Unlikely given BTF dump.

CONFIDENCE: HIGH

IMPACT: Blocked KERNEL_PROTOTYPED attach until port.

RECOMMENDATION:
Keep 7.0 wrappers version-gated (`ORCHESTRA_SCX_API_VERSION != 70012u` for 6.12). Do not boot in-tree VBox 6.12.96 bzImage (NVMe off).

IMPLEMENTATION MODIFIED: YES later (wrappers). At F6 capture time: NO.

---

FINDING ID: F2
TITLE: First CFS stress_suite memory phase filled /tmp tmpfs
SEVERITY: MEDIUM
TEST ID: T16
STATUS: FAIL then PASS on retry after `stress` installed

OBSERVATION:
Without `stress`, memory phase used `dd` into `/tmp` (7.7G tmpfs), wrote ~3.9G×2, suite aborted rc=1. Files deleted; `/tmp` returned to ~1% used.

EXPECTED:
Memory phase uses RAM (`stress`) or a filesystem with enough free space.

EVIDENCE:
`20260814-093036-kali` stress logs; later `20260814-095200-kali-auth/stress/orchestra-stress-*/results.csv` PASS.

REPRODUCIBILITY: 1/1 without stress; 10s and 30s PASS with stress.

FIRST FAILURE POINT: missing `stress` → dd fallback onto tmpfs.

LIKELY COMPONENT: workload / environment

MOST LIKELY CAUSE: tool gap, not CFS.

CONFIDENCE: HIGH

IMPACT: Reproducibility of first stress run; storage safety on tmpfs.

RECOMMENDATION:
Keep `stress` installed for RAM memory tests; do not use dd-to-tmpfs on 7.7G tmpfs.

IMPLEMENTATION MODIFIED: NO

---

FINDING ID: F-ACPI
TITLE: Stress-suite kernel-health WARN matches ACPI BIOS Error, not a panic
SEVERITY: INFORMATIONAL
TEST ID: T-stress-health
STATUS: PASS (false-positive WARN)

OBSERVATION:
`stress_suite.sh` health grep for `BUG` matches pre-existing ACPI `BIOS Error` in dmesg.

EXPECTED:
Health scan should not treat boot ACPI errors as ORCHESTRA/stress failures.

EVIDENCE:
Pre-campaign `dmesg_pre`; stress 10s/30s logs WARN with rc=0 overall suite after stress installed.

REPRODUCIBILITY: every health scan that greps BUG.

LIKELY COMPONENT: test script / hardware ACPI

MOST LIKELY CAUSE: substring match on BIOS Error.

CONFIDENCE: HIGH

IMPACT: Reporting only. Do not blame ORCHESTRA.

RECOMMENDATION:
Treat as known false positive; do not edit the script in this campaign.

IMPLEMENTATION MODIFIED: NO
