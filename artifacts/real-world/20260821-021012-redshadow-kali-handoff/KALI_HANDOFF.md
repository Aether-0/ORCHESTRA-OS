# ORCHESTRA-OS Kali real-machine handoff

This handoff prepares a separate Kali machine for the next controlled kernel
campaign. It is a runbook and evidence contract, not a new test program or a
source change.

## 1. Scope and current implementation

Use the repository at revision
68295dc134774c7699764b3234e40ac7c764cc5c or a later revision that has been
reviewed separately. The active kernel path is:

- BPF scheduler: kernel/sched_ext/orchestra_scx_stage7.bpf.c
- bridge: kernel/sched_ext/bridge/orchestra_bridge.c
- map-pinning loader: kernel/sched_ext/bridge/orchestra_loader.c
- existing bounded single-process workload:
  kernel/sched_ext/scripts/fixed_work.c

The current ABI explicitly targets ORCHESTRA_SCX_API_VERSION=70012 and the
Linux 7.0 scx_bpf_dsq_insert* / scx_bpf_dsq_move API. A different running
kernel is not automatically compatible. Do not silently reuse an old object,
rename kfuncs mechanically, or change the source during this test campaign.

The loader must be used for this object. It validates map schemas and pins the
runtime maps before struct_ops attach, which is required for the deferred-timer
map. Do not substitute bare bpftool struct_ops register for the loader.

The research signal bus, predictor, kernel S1/S2/S3/S4/Q, feedback controller,
and full Hybrid Safety Layer are not established as kernel-runtime features.
Keep those claims USERSPACE_VALIDATED, BLOCKED_NOT_IMPLEMENTED, or UNKNOWN as
appropriate; do not infer them from a scheduler attach.

## 2. Transfer and integrity

Transfer the current Git tree, not the dated orchestra-usb-final.zip scripts.
The USB bundle predates the current 7.0 loader/API state and contains broad
bpffs cleanup paths. On the target, record:

    cd /path/to/ORCHESTRA-OS
    git rev-parse --show-toplevel
    git rev-parse HEAD
    git status --short --branch
    sha256sum kernel/sched_ext/orchestra_scx_stage7.bpf.c \
      kernel/sched_ext/bridge/orchestra_bridge.c \
      kernel/sched_ext/bridge/orchestra_loader.c \
      kernel/sched_ext/include/orchestra_abi.h

If the tree is dirty, preserve and report the uncommitted paths. Do not call
the result a clean revision.

## 3. Safety gate before any kernel operation

Proceed only when the target operator has confirmed all of the following:

1. The machine is dedicated/disposable for scheduler testing and has no
   important unsaved work.
2. A known-good fallback kernel and local/remote recovery console are usable.
3. Current kernel, boot arguments, storage free space, thermal trip points,
   and pre-existing kernel warnings are recorded.
4. No unrelated sched_ext scheduler is active.
5. Existing BPF programs, maps, links, and bpffs pins are inventoried.
6. The target has enough disposable storage for the selected workload; raw
   disk tests are out of scope.

Capture this state before ORCHESTRA:

    date -Iseconds
    hostnamectl
    uname -a
    uname -r
    cat /etc/os-release
    lscpu
    nproc
    free -h
    df -h
    cat /proc/cmdline
    cat /sys/kernel/sched_ext/state 2>/dev/null || true
    sudo bpftool prog list
    sudo bpftool map list
    sudo bpftool link list
    find /sys/fs/bpf -maxdepth 2 -print 2>/dev/null
    sudo dmesg --ctime | tail -300
    sudo journalctl -k -b --no-pager | tail -300

Do not delete anything from /sys/fs/bpf to establish a clean state. If a
pre-existing pin or link cannot be attributed, stop and mark the runtime phase
BLOCKED_FOR_SAFETY.

Do not boot artifacts/kernel-v6.12.96-orchestra-stage8.bzImage on an NVMe
machine. Prior evidence records that image with NVMe disabled.

## 4. Kali prerequisites

First inspect versions without changing the host:

    command -v gcc clang llvm-config make bpftool python3 pkg-config
    gcc --version | head -1
    clang --version | head -1
    bpftool version
    pkg-config --modversion libbpf libelf
    dpkg-query -W linux-image-$(uname -r) linux-headers-$(uname -r) \
      linux-source-7.0 libbpf-dev libelf-dev zlib1g-dev 2>/dev/null || true

If a dependency is missing, record the exact blocker. Installation requires
separate target-host approval and was not performed during preparation. The
proposed Debian/Kali package set is:

    sudo apt update
    sudo apt install --no-install-recommends \
      build-essential clang llvm make bpftool libbpf-dev libelf-dev \
      zlib1g-dev dwarves python3 linux-source-7.0

Optional tools for later independent workload phases are stress, numactl,
linux-cpupower, perf, lm-sensors, and an scx_simple provider. Missing optional
tools block only the tests that require them; do not install them silently.

The source tree must contain the sched_ext headers used by the running kernel,
including:

    test -f "$KSRC/tools/sched_ext/include/scx/common.bpf.h"
    test -f "$KSRC/tools/lib/bpf_helpers.h"

Generic /usr/src/linux-headers-* alone is not sufficient. Verify the source
package or commit corresponds to the running kernel package. If exact
alignment cannot be established, stop at BLOCKED_KERNEL_CAPABILITY.

## 5. Userspace regression gate

From the target repository root, preserve stdout, stderr, and return codes for
each command. Run the existing gate exactly as documented:

    make clean
    make
    make check
    make test

Use actual counts from the output; historical counts in README files are not
acceptance evidence for a new target. A failure is diagnosed and recorded, not
fixed in this campaign.

Then run the existing capability checks:

    bash benchmarks/real-machine/sanity_check.sh
    bash kernel/sched_ext/scripts/check_kernel_config.sh

The required running-kernel options are CONFIG_BPF=y,
CONFIG_BPF_SYSCALL=y, CONFIG_BPF_JIT=y, CONFIG_DEBUG_INFO_BTF=y,
CONFIG_SCHED_CLASS_EXT=y, and CONFIG_BPF_EVENTS=y, plus
/sys/kernel/btf/vmlinux and /sys/kernel/sched_ext.

## 6. Out-of-tree target build

Use a campaign directory outside the source tree. The following is the
documented build flow with generated and output files kept in that directory:

    export REPO=/path/to/ORCHESTRA-OS
    export KSRC=/path/to/exact/linux-7.0.12-source
    export CAMPAIGN=/tmp/orchestra-realworld-$(date +%Y%m%d-%H%M%S)-$(hostname)
    mkdir -p "$CAMPAIGN"/{environment,build,baseline,kernel,sched_ext,raw}
    mkdir -p "$CAMPAIGN/build/include"

    sudo bpftool btf dump file /sys/kernel/btf/vmlinux format c \
      > "$CAMPAIGN/build/include/vmlinux.h"

    clang -O2 -target bpf -g -nostdinc -D__BPF__ \
      -I "$CAMPAIGN/build/include" \
      -I "$REPO/kernel/sched_ext/include" \
      -I "$KSRC/tools/lib" \
      -I "$KSRC/tools/bpf/bpftool/libbpf" \
      -I "$KSRC/include" -I "$KSRC/include/uapi" \
      -I "$KSRC/arch/x86/include" \
      -I "$KSRC/arch/x86/include/generated" \
      -I "$KSRC/tools/sched_ext/include" -I /usr/include/bpf \
      -Wno-missing-declarations -Wno-visibility \
      -Wno-address-of-packed-member \
      -c "$REPO/kernel/sched_ext/orchestra_scx_stage7.bpf.c" \
      -o "$CAMPAIGN/build/orchestra_scx_stage7.bpf.o"

    cc -O2 -Wall -Wextra -I "$REPO/kernel/sched_ext/include" \
      "$REPO/kernel/sched_ext/bridge/orchestra_bridge.c" \
      -o "$CAMPAIGN/build/orchestra_bridge" \
      $(pkg-config --cflags --libs libbpf)

    cc -O2 -Wall -Wextra -I "$REPO/kernel/sched_ext/include" \
      "$REPO/kernel/sched_ext/bridge/orchestra_loader.c" \
      -o "$CAMPAIGN/build/orchestra_loader" \
      $(pkg-config --cflags --libs libbpf)

    cc -O2 -Wall -Wextra \
      "$REPO/kernel/sched_ext/scripts/fixed_work.c" \
      -o "$CAMPAIGN/build/fixed_work"

    file "$CAMPAIGN/build/orchestra_scx_stage7.bpf.o" \
      "$CAMPAIGN/build/orchestra_bridge" \
      "$CAMPAIGN/build/orchestra_loader"
    sha256sum "$CAMPAIGN/build/include/vmlinux.h" \
      "$CAMPAIGN/build/orchestra_scx_stage7.bpf.o" \
      "$CAMPAIGN/build/orchestra_bridge" \
      "$CAMPAIGN/build/orchestra_loader" \
      "$CAMPAIGN/build/fixed_work"

A generated vmlinux.h and these build outputs are normal evidence artifacts;
they are not implementation changes. If compilation fails, preserve the first
relevant diagnostic and classify the cause before any retry.

## 7. Safe load/unload gate

Before loading, repeat the bpffs and sched_ext inventory. The target must be
disabled, and /sys/fs/bpf/orchestra/orchestra_sched must not already exist.
Do not remove another owner's objects.

Use only the current loader:

    sudo "$CAMPAIGN/build/orchestra_loader" --load \
      "$CAMPAIGN/build/orchestra_scx_stage7.bpf.o"
    cat /sys/kernel/sched_ext/state
    sudo "$CAMPAIGN/build/orchestra_bridge" --status

A registration return code is insufficient. Require state=enabled, valid
ABI/API/magic fields, the expected map schemas, and an owned link/pin set under
/sys/fs/bpf/orchestra. Preserve dmesg immediately after attach.

At the end of every runtime phase, unload only through the loader:

    sudo "$CAMPAIGN/build/orchestra_loader" --unload
    cat /sys/kernel/sched_ext/state
    find /sys/fs/bpf/orchestra -maxdepth 1 -print 2>/dev/null || true

Require disabled and removal of only the ORCHESTRA-owned pin directory. If
unload fails, preserve state and kernel logs; do not fall back to global bpffs
cleanup.

## 8. Ownership and action acceptance order

Do not begin comparison or stress claims until this gate is complete. Use the
existing fixed_work binary so the published PID is the long-lived worker itself;
do not use shell loops containing external sleep children.

For each trial, record the target PID, /proc/PID/stat processor field, affinity,
bridge generation, bridge status, and telemetry before and after the directive.
Keep the worker alive until the per-task line is captured.

1. Negative ownership: run fixed_work without --opt-in; its per-task enable,
   enqueue, and running evidence must not be attributed to ORCHESTRA.
2. Positive ownership: start one long-lived worker, run
   --opt-in --target-pid PID, publish RUN, and poll --status until the exact
   identity=TGID:TID:start_boottime record appears. Require positive per-task
   accepted, dispatched, and running counters.
3. RUN/YIELD: publish each to that same live TID. Separate requested,
   accepted, dispatched, effective, and fallback values. A global counter alone
   is not task ownership proof.
4. MIGRATE: choose an online CPU allowed by the worker's affinity. Start on
   CPU 0 with an allowed mask containing both 0 and the target CPU; never
   request CPU 3 from a task restricted to CPU 0. Require target CPU evidence
   in per-task telemetry and /proc/PID/stat, beginning with 3 repeats and
   expanding to 5 for a stronger claim.
5. SLEEP: use the bridge's monotonic --not-before-ns; demonstrate no execution
   before the deadline and deferred release after it. Acceptance or a short
   slice is not proof of sleep.
6. THROTTLE: use explicit --throttle-period-ns and
   --throttle-budget-ns; measure runtime duty cycle over the period. A smaller
   dispatch slice is not proof of throttling.
7. Invalid action: the current CLI rejects unknown action text and does not
   provide a safe direct invalid-map injector. Record CLI input validation as
   such; mark kernel unknown-action fallback
   BLOCKED_NO_SAFE_INJECTION_INTERFACE rather than fabricating a PASS.

If the worker exits before the required status or telemetry observation,
classify the action INCONCLUSIVE and retain the failed observation window.

## 9. Existing scripts: execution policy

Inspect, but do not run unmodified, these scripts on a machine containing any
unrelated BPF state:

- kernel/sched_ext/scripts/reproduce_stage7_runtime.sh — hard-coded source
  path and global struct_ops/pin cleanup
- kernel/sched_ext/scripts/p0_ownership_retest.sh — rm -rf /sys/fs/bpf/* and
  global link detachment
- kernel/sched_ext/scripts/stage8_validate.sh — hard-coded source path and
  global bpffs cleanup
- benchmarks/real-machine/benchmark_suite.sh — hard-coded /home/vagrant paths
  and broad link/pin handling
- benchmarks/real-machine/full_compare.sh — hard-coded paths and
  rm -rf /sys/fs/bpf/*

Do not edit these scripts during testing. Their unexecuted gates remain
BLOCKED_FOR_SAFETY or BLOCKED_PATH_ASSUMPTION.

stress_suite.sh may be considered for a CFS-only baseline after the storage,
thermal, and tool gates pass. Its fallback memory path writes large files to
/tmp; require the stress tool or an explicitly adequate disposable filesystem.
Do not run its orchestra mode as an ownership or performance proof before the
per-task gate above.

## 10. Evidence and stop rules

Keep the approved broad checklist in
ORCHESTRA_OS_Real_World_Machine_Test_Checklist.docx; this handoff does not
duplicate it. Store campaign output outside source files with:

- environment and package/source identity
- command, working directory, timestamp, return code, stdout, and stderr
- BTF/object/bridge/loader hashes
- bpftool map/link/program snapshots
- scheduler state transitions
- bridge status and per-task telemetry
- pre/post dmesg and thermal/storage readings
- raw workload measurements and first failures

Immediately stop the current phase after a panic, repeated oops, filesystem
corruption, scheduler lockup, hung-task/RCU stall caused by the test, unsafe RT
interference, data loss, or a serious thermal event. Preserve evidence before
recovery. Do not reboot automatically; if a reboot becomes necessary, write a
resume note and stop the campaign at BLOCKED_REBOOT_REQUIRED.

## 11. Acceptance boundary

The next target campaign may claim KERNEL_PROTOTYPED for the target only if it
proves source-hashed build, verifier/attach, ownership, and clean unload.
It may claim EXPERIMENTALLY_VALIDATED for a specific action only with
repeatable per-task effective-outcome evidence and an explicit protocol.
Nothing in this handoff authorizes deployment or upgrades the prior physical
Kali result beyond PARTIALLY_VALIDATED.
