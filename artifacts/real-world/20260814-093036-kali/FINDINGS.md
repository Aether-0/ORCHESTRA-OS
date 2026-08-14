# Findings

Sorted by severity. IMPLEMENTATION MODIFIED: NO for every finding.

---

FINDING ID: F1  
TITLE: Kernel sched_ext prototype cannot be built or loaded on this physical host  
SEVERITY: HIGH  
TEST ID: T5, T6, T7  
STATUS: BLOCKED  

OBSERVATION:  
Documented BPF compile failed with `scx/common.bpf.h` not found. Bridge link failed with `cannot find -lbpf`. `bpftool` is not installed. Kernel source `~/src/linux-v6.12.96` is absent. `include/vmlinux.h` is absent. Running kernel is `7.0.12+kali-amd64`. BPF source comments target Linux v6.12 `scx_bpf_dispatch*` names. `/sys/kernel/sched_ext/state` remained `disabled` for the entire campaign. `enable_seq=0`.

EXPECTED:  
On a physical pilot host matching the VBox gate, generate `vmlinux.h`, compile `orchestra_scx_stage7.bpf.c` and the bridge, register struct_ops, and observe `sched_ext/state=enabled`.

EVIDENCE:  
- `raw/bpf_compile.stderr`  
- `raw/bridge_compile.stderr`  
- `environment/tools_cont.txt`  
- `environment/os.txt` (`Linux kali 7.0.12+kali-amd64`)  
- `kernel/sched_ext/orchestra_scx_stage7.bpf.c` lines 5–8  

REPRODUCIBILITY: 1/1 compile attempts failed immediately.  

FIRST FAILURE POINT: Missing sched_ext BPF headers / kernel source include path. Independently, missing libbpf link library and bpftool.

LIKELY COMPONENT: Build / kernel config / libbpf / bpftool mismatch / environment.

MOST LIKELY CAUSE: This Kali rolling host has sched_ext *enabled in the running kernel* but lacks the userspace/build toolchain and the v6.12 kernel source tree the prototype is written against.

ALTERNATIVE CAUSES: Source compile defect on clang 21; BTF incompatibility with 7.0. Those were not reached.

EVIDENCE AGAINST ALTERNATIVES: Failure is a missing header and missing `-lbpf`, before any BPF verifier run.

CONFIDENCE: HIGH  

IMPACT: Correctness / claim scope. No physical-machine KERNEL_PROTOTYPED result on this host.

RECOMMENDATION: With explicit package-install authorization: install `bpftool`, `libbpf-dev`, `libelf-dev`; provide matching kernel headers/source; decide whether to boot a 6.12.x sched_ext kernel or perform a reviewed API port to 7.0 (the source forbids a compile-only rename). Then rebuild, load, and prove ownership.

IMPLEMENTATION MODIFIED: NO.

---

FINDING ID: F2  
TITLE: Existing stress_suite memory fallback filled /tmp tmpfs and aborted the suite  
SEVERITY: MEDIUM  
TEST ID: T16  
STATUS: FAIL  

OBSERVATION:  
`stress_suite.sh 10 cfs` completed the 24-worker CPU phase (10s, 0 errors). `stress` is not installed. The dd fallback wrote two ~3.9Gi files to `/tmp`. `/tmp` is a 7.7Gi tmpfs. `/tmp` reached 100% full. Suite returned rc=1 during the memory phase. I/O and mixed phases did not run. After deleting `/tmp/orchestra-stress-1` and `/tmp/orchestra-stress-2`, `/tmp` returned to 1% used. No OOM killer lines were found in the captured dmesg tail.

EXPECTED:  
Memory stress should complete without exhausting the filesystem used for disposable files, then I/O and mixed phases should run.

EVIDENCE:  
- `stress/stress_10_cfs.stdout`  
- `stress/mem_fail_diag.txt` (`tmpfs 7.7G 100%`; `stress binary: missing`)  
- leftover sizes 3.9G + 3.9G before cleanup  

REPRODUCIBILITY: 1/1 on this host with `stress` absent. Not re-run (safety).

FIRST FAILURE POINT: Memory fallback path writing 50% of RAM as files onto a tmpfs smaller than that allocation.

LIKELY COMPONENT: Workload / test script vs host layout.

MOST LIKELY CAUSE: Script assumes either `stress` (anonymous RAM) or a `/tmp` large enough for `STRESS_MB` file writes. Here RAM=15Gi so STRESS_MB=7837, tmpfs=7.7Gi.

ALTERNATIVE CAUSES: OOM; disk failure. Unlikely: no OOM records; NVMe root had 23G free; problem was `/tmp` tmpfs.

EVIDENCE AGAINST ALTERNATIVES: Exact file sizes and `df /tmp`.

CONFIDENCE: HIGH  

IMPACT: Reproducibility of the stock stress suite; not an ORCHESTRA scheduler defect (scheduler was not loaded).

RECOMMENDATION: Do not edit the script in this campaign. Future work: run with `stress` installed, or point disposable files at a larger disk-backed directory (requires script change by developers). Do not re-run this fallback on 15Gi hosts with 7.7Gi tmpfs.

IMPLEMENTATION MODIFIED: NO.

---

FINDING ID: F3  
TITLE: Userspace orchestra last-row Q varied widely across three 4s runs  
SEVERITY: LOW  
TEST ID: T11u, T12u  
STATUS: INCONCLUSIVE (for a stability claim)  

OBSERVATION:  
Same binary, seed 104729, 4 workers, duration 4s, interval 100ms. Last-row Q: 0.79176016, 0.51911308, 0.29757219. S1/S2/S3/S4 also moved. Baseline mode last-row Q was 1.0 on all three runs. Tamper run last-row Q=0 with rejected_frames=32.

EXPECTED:  
Exploratory N=3 can show variance. A strong experimental Q claim needs longer duration, more reps, and kernel ownership. Baseline Q=1 is expected for the observed-state reference, not proof of coordination quality.

EVIDENCE: `workload/paper_cpu_s1s4_summary.txt`

REPRODUCIBILITY: 3/3 orchestra short runs completed; Q not stable at last row.

FIRST FAILURE POINT: Using last-row of a 4s userspace run as a coordination claim.

LIKELY COMPONENT: Instrumentation / workload duration / userspace policy exploration.

MOST LIKELY CAUSE: Short horizon plus per-tick coordination dynamics; CFS still dispatches.

ALTERNATIVE CAUSES: Nondeterminism from other host load. Possible; loadavg was nonzero.

CONFIDENCE: MEDIUM  

IMPACT: Claim scope for userspace Q on this machine.

RECOMMENDATION: Treat these as USERSPACE_VALIDATED telemetry samples, not physical scheduler Q. Use the committed paper-cpu benchmark runner with an authorized v7 schema/manifest if a statistical userspace claim is required.

IMPLEMENTATION MODIFIED: NO.

---

FINDING ID: F4  
TITLE: Stock real-machine scripts hard-code VirtualBox paths  
SEVERITY: INFORMATIONAL  
TEST ID: T15, T17  
STATUS: N/A as a product FAIL  

OBSERVATION:  
`benchmark_suite.sh` and `full_compare.sh` default BPF/bridge paths to `/home/vagrant/Documents/ORCHESTRA-OS/...`. On this host those files do not exist. CFS branches still ran. ORCHESTRA branches were skipped. `full_compare.sh` did not execute `rm -rf /sys/fs/bpf/*` because the BPF file test failed first.

EXPECTED:  
Location-independent paths or documented environment variables. `ORCHESTRA_BPF` exists in benchmark_suite; full_compare hard-codes BPF.

EVIDENCE: `benchmarks/real-machine/benchmark_suite.sh` line 10; `full_compare.sh` line 9; `workload/benchmark_suite.stdout` “BPF object missing”.

REPRODUCIBILITY: Always on this tree/host.

LIKELY COMPONENT: Test infrastructure.

MOST LIKELY CAUSE: Scripts written for the Vagrant/VBox layout.

CONFIDENCE: HIGH  

IMPACT: Reproducibility on bare metal even after toolchain install, unless env vars are set.

RECOMMENDATION: Developers should make paths relative to the repo. Testers can export `ORCHESTRA_BPF`/`ORCHESTRA_BRIDGE` once objects exist. Do not run `full_compare` ORCHESTRA branch on hosts with unrelated bpffs pins.

IMPLEMENTATION MODIFIED: NO.

---

FINDING ID: F5  
TITLE: Pre-existing ACPI BIOS errors and journal time jump  
SEVERITY: INFORMATIONAL  
TEST ID: T0  
STATUS: PASS (recorded, not blamed on ORCHESTRA)  

OBSERVATION:  
Boot dmesg contains ACPI BIOS Error CreateField length zero and AE_AML_BUFFER_LIMIT. `systemd-journald: Time jumped backwards, rotating` at 09:18:53. No panic/hung_task/RCU stall attributed to tests.

EVIDENCE: `environment/dmesg_pre.txt`, `stress/dmesg_post_cpu60.txt`

CONFIDENCE: HIGH  

IMPACT: Do not attribute these ACPI lines to ORCHESTRA.

IMPLEMENTATION MODIFIED: NO.
