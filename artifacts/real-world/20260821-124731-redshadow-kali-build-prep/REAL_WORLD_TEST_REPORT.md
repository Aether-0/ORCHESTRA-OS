# ORCHESTRA-OS real-machine readiness report — Kali

## Outcome

The repository is userspace-regression ready and the bridge/loader preparation
artifacts are built. The next physical scheduler run is not yet attach-ready:
the BPF object must be rebuilt on the target from an exact source/BTF match.

The current host is:

- Kali Linux 7.0.12+kali-amd64
- 8 logical CPUs, Intel Core i5-10310U
- 30 GiB RAM, 26 GiB free on /
- sched_ext state: disabled
- running-kernel BTF SHA-256:
  3f39484930b332629a5864a1a703b0a39320cc1584f6e8a00dfbc6375b58ec76

Repository state is dirty before this campaign. Existing user paths were
preserved. The scoped source guard was clean:
git diff --name-only -- kernel/sched_ext benchmarks Makefile README.md AGENTS.md
returned no paths.

## Evidence summary

| Area | Result | Evidence |
|---|---|---|
| Repository identity | PASS | HEAD 68295dc134774c7699764b3234e40ac7c764cc5c |
| Real-machine sanity gate | PASS | sanity_check.sh, return 0 |
| Kernel config gate | PASS | check_kernel_config.sh, return 0 |
| make clean | PASS | return 0 |
| make | PASS | return 0; demo compiled with -Werror |
| make check | PASS | return 0 |
| make test, first direct run | PASS | return 0 |
| make test, captured repeat 1 | INTERMITTENT FAILURE | return 2; signal-stop wrapper exit 137 |
| integration reruns | PASS 3/3 | existing tests/integration/run.sh, each return 0 |
| make test, captured repeat 2 | PASS | return 0; complete log and JSON preserved |
| running-kernel vmlinux.h | BUILT | build/vmlinux.h, BTF-derived |
| bridge | BUILT | build/orchestra_bridge |
| loader | BUILT_WITH_PREP_INPUTS | build/orchestra_loader |
| fixed workload | BUILT | build/fixed_work |
| target BPF object | BLOCKED_KERNEL_SOURCE_MISMATCH | no object claimed or used |
| sched_ext load/unload | NOT RUN | intentionally deferred to root-capable target |

The captured regression records are:

- test-run/test-result.json: failed repeat, return code 2; log SHA-256
  d1f6ee75a2dc85aff22a53180323ea4db306cfc7d9782ce80a907afab236596e
- test-run-2/test-result.json: passing repeat, return code 0; log SHA-256
  c972b27359e632fe8bede756001e44f7c24816c29f3ec2772ee064f64a371572

The failed repeat reached the existing signal-stop case, emitted Finished.
and 20 CSV rows, then its documented 3-second timeout plus 2-second
kill-after window observed Killed and return 137. No OOM, panic, RCU stall,
or scheduler fault was found in the accessible kernel log. Three subsequent
direct integration runs passed. Treat this as an intermittent userspace test
teardown observation, not as erased evidence and not as a kernel result.

## Tool and source blockers

Required tools reported present: gcc 15.3.0, clang 21.1.8, GNU make 4.4.1,
bpftool 7.7.0, Python 3.14.6, mpstat, pidstat, and lstopo-no-graphics.

Missing or incomplete inputs:

- llvm-config is missing.
- /usr/include/bpf/libbpf.h is missing.
- pkg-config --modversion libbpf libelf reports both packages missing.
- /usr/src/linux-headers-7.0.12+kali-* exists but does not contain the
  sched_ext tool headers required by the BPF build.
- /home/aether/Documents/linux contains the needed sched_ext headers but is
  commit 0d839570765118029aa8bf4a95444c6a11aacf85, v7.2-rc6-59-g0d8395707651,
  kernel version 7.2.0-rc6, not the running 7.0.12 kernel.
- Optional tools missing: numactl, sensors, perf, stress.

Do not install packages silently. On the target, resolve the exact source and
development-package inputs under separate operator authorization.

## Built artifacts

All outputs are outside source files:

| Artifact | SHA-256 |
|---|---|
| build/vmlinux.h | 96b223c8eaa9763f6caa0998188cf632aa0133c096bf526edc0043db3e675a51 |
| build/orchestra_bridge | 9ac00bca5b3a8118339662bb128fb25984895b6a6664ed7419b63404914ef538 |
| build/orchestra_loader | 9448e2fa0b99e45cf192662e33cd9241cdf93f1f868015de150ad85aa542fda0 |
| build/fixed_work | 6534eb8a01fdc707ad4790a65fcfd3817ac03a33e616c0f48b09b681ded9eaa1 |

The authoritative complete hash list is in COMMANDS.log and RESULTS.json.
The vmlinux.h is valid only for the BTF hash recorded above; do not transfer
it to a different kernel.

The loader must be used for the current object because the deferred timer map
must be pinned before struct_ops attach. Do not replace it with bare
bpftool struct_ops register. Do not run repository scripts that perform
global bpffs cleanup.

## Next target procedure

On the next physical Kali target:

1. Record the repository commit/status, uname, kernel config, BTF hash,
   /sys/kernel/sched_ext/state, dmesg/journal, storage, thermal state, and
   all existing BPF programs/maps/links/pins as root.
2. Confirm the machine is disposable/recoverable and sched_ext is disabled.
3. Verify a full kernel source tree matches uname -r and contains
   tools/sched_ext/include/scx/common.bpf.h; do not use generic headers or
   this host's 7.2 source.
4. Generate vmlinux.h from the target's own /sys/kernel/btf/vmlinux into a
   new campaign build directory.
5. Compile orchestra_scx_stage7.bpf.c, bridge, loader, and fixed_work in that
   directory. Hash every output.
6. Load only through orchestra_loader --load, verify enabled state, exact map
   schemas, bridge status, and ORCHESTRA-owned pins.
7. Run the negative and positive per-TID ownership gates with the existing
   fixed_work binary.
8. Validate RUN, YIELD, MIGRATE, SLEEP, and THROTTLE separately. Distinguish
   requested, accepted, dispatched, effective, and fallback telemetry.
9. Unload only through orchestra_loader --unload; require disabled state and
   removal only of ORCHESTRA-owned pins.
10. Run baseline and comparison phases only after ownership is proven. Keep the
    prior physical Kali limitations: no Q/predictor/controller kernel claims
    without direct implementation and telemetry evidence.

The detailed command-level runbook is the existing
../20260821-021012-redshadow-kali-handoff/KALI_HANDOFF.md.
