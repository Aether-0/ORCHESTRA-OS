# ORCHESTRA-OS

Predictive, cryptographically protected, hierarchical, signal-coordinated scheduling architecture for Linux.

**Current real-machine handoff (2026-08-22):** The Kali capability and userspace gates passed, and the Stage 7/v8 BPF object, bridge, and loader now build out of tree against the running 7.0.12 BTF using explicitly recorded exact-version UAPI/generator inputs. The kernel prototype includes the bounded fixed-point `orch_signal` transport and fail-closed `--require-signal` gate, plus the source/build-validated v8 runtime-policy/controller path; a fresh verifier/attach/ownership gate still requires non-interactive root access.

**Current preparation status:** The 2026-08-22 campaign is ready for the next controlled target session; target-side verifier/attach, signal-gate, and runtime ownership evidence remain required.

**Status:** Kernel-prototyped. VirtualBox runtime gate passed on 2026-08-14. First physical-machine campaign on Kali 7.0.12 (HP Pro Tower 280 G9) is **PARTIALLY_VALIDATED**: userspace tests passed; 7.0-ported Stage-7 BPF loaded/unloaded cleanly; canonical kernel actions were **not** shown effective. Not experimentally validated, not deployment-ready. Dedicated ORCHESTRA vs CFS vs `scx_simple` benchmarking is deferred.

---

## Quick Links

| What | Link |
|------|------|
| **Physical machine Kali report** (HTML, 2026-08-14; this host) | [ORCHESTRA_Physical_Machine_Kali_Report_2026-08-14.html](./ORCHESTRA_Physical_Machine_Kali_Report_2026-08-14.html) |
| **Physical campaign evidence** (checklist + findings) | [artifacts/real-world/20260814-104600-kali-checklist/](./artifacts/real-world/20260814-104600-kali-checklist/) |
| **Next Kali real-machine handoff** (2026-08-21) | [KALI_HANDOFF.md](./artifacts/real-world/20260821-021012-redshadow-kali-handoff/KALI_HANDOFF.md) |
| **Kali build-prep evidence** (2026-08-21) | [EXECUTIVE_SUMMARY.md](./artifacts/real-world/20260821-124731-redshadow-kali-build-prep/EXECUTIVE_SUMMARY.md) · [REAL_WORLD_TEST_REPORT.md](./artifacts/real-world/20260821-124731-redshadow-kali-build-prep/REAL_WORLD_TEST_REPORT.md) |
| **Fixed-point signal bridge follow-up** (2026-08-22) | [IMPLEMENTATION_VALIDATION_20260822_SIGNAL.md](./artifacts/real-world/20260821-implementation-validation/IMPLEMENTATION_VALIDATION_20260822_SIGNAL.md) · [IMPLEMENTATION_MATRIX_20260822.md](./artifacts/real-world/20260821-implementation-validation/IMPLEMENTATION_MATRIX_20260822.md) |
| **Metrics-v7 contract follow-up** (2026-08-22) | [IMPLEMENTATION_VALIDATION_20260822_METRICS_V7.md](./artifacts/real-world/20260821-implementation-validation/IMPLEMENTATION_VALIDATION_20260822_METRICS_V7.md) |
| **Deep Kernel + C Source Code Audit** (HTML, 2026-08-14; VM/source gate) | [ORCHESTRA_Deep_Kernel_C_Source_Code_Audit_2026-08-14.html](./output/doc/ORCHESTRA_Deep_Kernel_C_Source_Code_Audit_2026-08-14.html) |
| **Deep Kernel + Algorithm Code Review** (HTML, 2026-08-14) | [ORCHESTRA_Deep_Kernel_Algorithm_Code_Review_2026-08-14.html](./output/doc/ORCHESTRA_Deep_Kernel_Algorithm_Code_Review_2026-08-14.html) |
| **Runtime Validation Report** (HTML, 2026-08-14) | [ORCHESTRA_Runtime_Validation_Report_2026-08-14.html](./ORCHESTRA_Runtime_Validation_Report_2026-08-14.html) |
| **VirtualBox Runtime Evidence** (Markdown, 2026-08-14) | [SUMMARY.md](./artifacts/test-results/vbox-runtime-2026-08-14/SUMMARY.md) |
| **VirtualBox Post-Fix Benchmark Comparison** (HTML, 2026-08-14) | [ORCHESTRA_VM_Benchmark_Comparison_2026-08-14.html](./ORCHESTRA_VM_Benchmark_Comparison_2026-08-14.html) |
| **USB Deployment Kit** (everything for real machine) | [orchestra-usb-final.zip](./orchestra-usb-final.zip) |
| **Final Report** (Markdown + Mermaid flowcharts) | [ORCHESTRA-OS-Final-Report.md](./ORCHESTRA-OS-Final-Report.md) |
| **Final Report** (PDF) | [ORCHESTRA-OS-Final-Report.pdf](./ORCHESTRA-OS-Final-Report.pdf) |
| **Known Recommendations & Fixes** (Markdown) | [known_recommand_fix.md](./known_recommand_fix.md) |
| **Before / After Report** (HTML, ownership fix vs Stage 8/9) | [ORCHESTRA_Before_After_Report.html](./artifacts/test-results/2026-08-13/vbox-mcp/ORCHESTRA_Before_After_Report.html) |
| **P0 ownership retest** (VirtualBox, after recommended fixes) | [p0-ownership-retest/](./artifacts/test-results/2026-08-13/vbox-mcp/p0-ownership-retest/) |
| **P0 owned 5s bench CSV** (CFS / scx_simple / ORCHESTRA) | [p0-owned-bench/](./artifacts/test-results/2026-08-13/vbox-mcp/p0-owned-bench/) |
| **Kernel Benchmark Report** (HTML + graphs, VirtualBox) | [ORCHESTRA_Kernel_Benchmark_Report.html](./artifacts/test-results/2026-08-13/vbox-mcp/ORCHESTRA_Kernel_Benchmark_Report.html) |
| **Kernel Improvement Report** (HTML findings & fix map) | [ORCHESTRA_Kernel_Improvement_Report.html](./artifacts/test-results/2026-08-13/vbox-mcp/ORCHESTRA_Kernel_Improvement_Report.html) |
| **VBox Test Ladder Summary** | [SUMMARY.md](./artifacts/test-results/2026-08-13/vbox-mcp/SUMMARY.md) |
| **Architecture Decisions** (12 ADRs) | [docs/adr/](./docs/adr/) |
| **Kernel BPF Scheduler Source** | [kernel/sched_ext/](./kernel/sched_ext/) |
| **Real-Machine Benchmarks** | [benchmarks/real-machine/](./benchmarks/real-machine/) |
| **Research Paper** | [orchestra os tdps final 6 july.pdf](./orchestra%20os%20tdps%20final%206%20july.pdf) |
| **Release Package** (20 docs) | [release/](./release/) |
| **Final Documentation** (18 docs + flowcharts) | [docs/final_report/](./docs/final_report/) |
| **Security Threat Model** | [docs/security/stage8-threat-model.md](./docs/security/stage8-threat-model.md) |

---

## Project Map

```
ORCHESTRA-OS/
│
├── orchestra_paper_cpu_demo/      Userspace prototype (C11, RL, controller)
│   ├── orchestra_paper_cpu.c       Canonical userspace algorithm implementation
│   ├── Makefile                    Build
│   └── README.md                   Usage
│
├── kernel/sched_ext/               Linux sched_ext kernel scheduler
│   ├── orchestra_scx_stage7.bpf.c  BPF scheduler (v8 core; compatibility filename)
│   ├── orchestra_scx.bpf.c         Stage 6 minimal scheduler
│   ├── include/
│   │   ├── orchestra_bridge_v1.h   Bridge contract (versioned structs)
│   │   ├── orchestra_kernel_v8.h   Kernel-resident adaptive ABI v8
│   │   └── orchestra_scx.h         Scheduler types
│   ├── bridge/
│   │   └── orchestra_bridge.c      Userspace bridge CLI
│   └── scripts/
│       ├── check_kernel_config.sh  Verify CONFIG_SCHED_CLASS_EXT
│       ├── build_stage7_out_of_tree.sh  Target-matched build
│       ├── p0_ownership_retest.sh       Exact-TID runtime gate
│       ├── reproduce_stage7_runtime.sh  Safe Stage 7 wrapper
│       └── stage8_validate.sh            Safe Stage 8 wrapper
│
├── benchmarks/                     Performance testing
│   ├── real-machine/               ** USB STICK — RUN ON REAL HARDWARE **
│   │   ├── sanity_check.sh         Verify machine, kernel, tools
│   │   ├── stress_suite.sh         60s CPU + Memory + I/O + Mixed
│   │   ├── benchmark_suite.sh      CFS vs scx_simple vs ORCHESTRA
│   │   ├── full_compare.sh         Full comparison with CSV export
│   │   └── README.md               Benchmark usage guide
│   ├── stage8/
│   │   └── benchmark_runner.py     Stage 8 Python harness
│   └── stage9/
│       └── benchmark_compare.sh    Stage 9 CFS vs ORCHESTRA
│
├── tests/                          Validation
│   ├── unit/                       30 named unit tests (GCC + Clang)
│   ├── integration/                5 scenarios + 34 CSV validator tests
│   └── test_orchestra_paper_cpu.c  Unit test source
│
├── docs/                           Documentation
│   ├── adr/                        12 Architecture Decision Records
│   ├── final_report/               18-section final report + flowcharts
│   ├── architecture/               sched_ext preparation design
│   ├── kernel/                     VirtualBox bringup, kernel validation
│   ├── security/                   Threat model + hardening checklist
│   └── experiments/                Methodology + results
│
├── release/                        Professor submission package
│   ├── FINAL_REPORT.md
│   ├── ARCHITECTURE.md
│   ├── REPRODUCTION_GUIDE.md
│   └── ... (20 documents)
│
├── artifacts/                      Kernel images, configs, test results
├── experiments/                    JSON manifests + metric schemas (v2-v7)
├── tools/                          Benchmark runner, PDF report generator
│
├── ORCHESTRA_Physical_Machine_Kali_Report_2026-08-14.html  ** Physical Kali campaign **
├── ORCHESTRA-OS-Final-Report.md    ** Single-file complete report **
├── ORCHESTRA-OS-Final-Report.pdf   ** Single-file PDF report **
├── orchestra-usb-final.zip         ** USB deployment kit **
├── AGENTS.md                       Research governance
├── Makefile                        Build orchestration
└── README.md                       This file
```

---

## 1. Build and Test (Userspace)

```bash
make clean && make && make test
```

**Expected:** 30/30 named unit tests under each compiler/transport pass, 24 benchmark-validator tests, 4 signal-publication runner tests, 34 CSV-validator tests, and 5 bounded integration scenarios.

### Run the userspace demo

```bash
./orchestra_paper_cpu_demo/orchestra_paper_cpu \
  --workers 4 --duration 10 --mode orchestra --seed 42
```

---

## 2. Real-Machine Kernel Setup

> **Physical campaign (2026-08-14, this Kali host):** attach/unload **PASS** after a 7.0 `scx_bpf_dsq_insert*` port; MIGRATE/SLEEP **not effective** as observed. See the [Kali physical report](./ORCHESTRA_Physical_Machine_Kali_Report_2026-08-14.html). Do **not** boot `artifacts/kernel-v6.12.96-orchestra-stage8.bzImage` on NVMe hardware (that image has NVMe disabled).
>
> **Safety gate:** The VirtualBox runtime gate still applies as 6.12 guest evidence. Physical use remains a controlled pilot: disposable host, rollback, abort thresholds, no production workloads. This is not authorization for deployment. VM evidence: [runtime validation report](./ORCHESTRA_Runtime_Validation_Report_2026-08-14.html).

### Current Kali real-machine handoff (2026-08-21)

Use the [Kali handoff runbook](./artifacts/real-world/20260821-021012-redshadow-kali-handoff/KALI_HANDOFF.md) and the [build-prep report](./artifacts/real-world/20260821-124731-redshadow-kali-build-prep/REAL_WORLD_TEST_REPORT.md) for the next physical session.

Before a kernel operation, verify root access, recovery capability, storage and thermal headroom, sched_ext disabled state, and all existing BPF programs, maps, links, and pins. Build out-of-tree from a full kernel source tree matching the target uname -r and generate vmlinux.h from that target's own BTF. Generic linux-headers packages, this host's generated vmlinux.h, and the available Linux 7.2-rc6 source are not substitutes for a matching Kali target source; an exact-version UAPI/generator override must remain explicitly hashed in build evidence. Prove per-TID sched_ext ownership before any benchmark or stress comparison.

### Prerequisites
- Linux 6.12+ with `CONFIG_SCHED_CLASS_EXT=y` and `CONFIG_DEBUG_INFO_BTF=y`
- `gcc`, `clang`, `make`, `bpftool`, `libbpf-dev`, `libelf-dev`, `zlib1g-dev`
- Root access

### Quick Install from USB

The dated USB bundle is historical evidence, not the current Kali runbook. Inspect its scripts before use; the current handoff avoids broad bpffs cleanup and requires target-matched source/BTF inputs.

```bash
unzip orchestra-usb-final.zip && cd orchestra-usb-final
bash scripts/sanity_check.sh         # Check environment
bash scripts/install.sh              # Install kernel + build userspace + bridge
sudo reboot                          # Boot ORCHESTRA kernel
bash scripts/build_bpf.sh            # Compile BPF scheduler against running BTF
bash scripts/load.sh                 # Load scheduler
bash scripts/benchmark_suite.sh      # Compare CFS vs scx_simple vs ORCHESTRA
bash scripts/stress_suite.sh 120     # 2-minute stress test
bash scripts/unload.sh               # Remove scheduler
```

### Historical in-tree BPF build example

The following older example is retained for reference. For the next Kali
session, use the target-matched, out-of-tree builder below.

### Target-matched out-of-tree Stage 7 build

The builder refuses a kernel-source version mismatch, keeps generated files
outside the repository, generates `vmlinux.h` from the running kernel BTF,
generates libbpf helper definitions from the selected matching UAPI header,
and emits hashes for the BPF object, bridge, and loader.

```bash
ORCHESTRA_KERNEL_SRC=/path/to/linux-<exact-running-version> \
ORCHESTRA_BUILD_DIR=/tmp/orchestra-stage7-build \
  bash kernel/sched_ext/scripts/build_stage7_out_of_tree.sh
```

If a distro/source export omitted the tools UAPI copy, provide the exact
same-version kernel UAPI header with `ORCHESTRA_BPF_UAPI`. If it omitted
`scripts/bpf_doc.py`, provide a reviewed generator with `ORCHESTRA_BPF_DOC`;
the selected paths are recorded in the build log and are not evidence of a
complete kernel source export. The command exits `2` with a `BLOCKED_*`
reason when required inputs are missing. It does not install packages or
modify `/sys/fs/bpf`.

### Historical low-level BPF command

```bash
cd kernel/sched_ext
sudo bpftool btf dump file /sys/kernel/btf/vmlinux format c > include/vmlinux.h
clang -O2 -target bpf -g -nostdinc -D__BPF__ \
  -I include -I $KSRC/tools/lib -I $KSRC/include -I $KSRC/include/uapi \
  -I $KSRC/arch/x86/include -I $KSRC/arch/x86/include/generated \
  -I $KSRC/tools/sched_ext/include -I /usr/include/bpf \
  -Wno-missing-declarations -Wno-visibility -Wno-address-of-packed-member \
  -c orchestra_scx_stage7.bpf.c -o orchestra_scx_stage7.bpf.o
```

### Historical Bridge CLI build example

```bash
cc -O2 -Wall -Wextra -I kernel/sched_ext/include \
  kernel/sched_ext/bridge/orchestra_bridge.c \
  -o bridge -lbpf
```

### Load / Unload

For the current Kali campaign, use the target-matched binaries and loader
order in the handoff. Do not use the historical in-tree paths below as proof
of target compatibility.

On Linux 7.0 (this Kali host) the BPF object must be built against `scx_bpf_dsq_insert*` (`ORCHESTRA_SCX_API_VERSION=70012`). Pin maps **before** attach via the loader. Do not wipe all of `/sys/fs/bpf`.

```bash
cd kernel/sched_ext
sudo ./bridge/orchestra_loader --load ./orchestra_scx_stage7.bpf.o
cat /sys/kernel/sched_ext/state          # enabled
sudo ./bridge/orchestra_bridge --status
sudo ./bridge/orchestra_bridge --publish --action RUN --target-pid <PID>
sudo ./bridge/orchestra_loader --unload
cat /sys/kernel/sched_ext/state          # disabled
```

Bare `bpftool struct_ops register` is insufficient for this object (timer map). Scripts that `rm -rf /sys/fs/bpf/*` were not used on this host.

---

## 3. Real-Machine Benchmarks

### Sanity Check

```bash
bash benchmarks/real-machine/sanity_check.sh
```

Checks: kernel version, CPU, RAM, CONFIG_SCHED_CLASS_EXT, BTF, tools.

### Stress Suite (4 workloads, CSV output)

```bash
sudo bash benchmarks/real-machine/stress_suite.sh 120
```

| Test | What It Does |
|------|-------------|
| CPU | N workers × 100% spin loop |
| Memory | 50% RAM allocation + pressure |
| I/O | Parallel read/write to /tmp |
| Mixed | Half CPU + half I/O |
| Health | Kernel log scan for panics/stalls |

Results: `/tmp/orchestra-stress-<timestamp>/results.csv`

### Benchmark Suite (CFS vs scx_simple vs ORCHESTRA)

```bash
sudo bash benchmarks/real-machine/benchmark_suite.sh
```

Tests 1, 2, 4, 8 workers × 30 seconds each. Outputs CSV with elapsed_ms and context switches.

### Full Comparison

```bash
sudo bash benchmarks/real-machine/full_compare.sh
```

Runs all three schedulers through all worker counts. Exports to `/tmp/orchestra-compare-<timestamp>/results.csv`.

### Expected Overhead (historical estimate — not a Kali measurement)

| Scheduler | Relative to CFS |
|-----------|----------------|
| CFS | 1.00× (baseline) |
| scx_simple | ~1.02× (not installed on this Kali host) |
| ORCHESTRA | ~1.20× (design estimate only) |

These figures are **not** results from the 2026-08-14 physical campaign. One 4-worker 8s run while ORCHESTRA was loaded finished in 7997 ms versus CFS ~7993 ms (n=1, full-switch, ownership not isolated). A proper comparison is deferred.

---

## 4. Bridge CLI Reference

```
Usage: ./bridge <command>

--status              Print scheduler state, magic, generation, telemetry
--publish             Publish a directive
  --action RUN|YIELD|MIGRATE|THROTTLE|SLEEP
  --target-pid <pid>
  --target-cpu <cpu>  (default: any)
  --slice-ns <ns>     (0 = nominal)
  --require-signal    Fail closed unless a current kernel signal frame exists
  --dry-run            Validate without mutation
--signal-publish      Publish a bounded fixed-point `orch_signal` frame
  --signal-sequence <n> and optional prediction/metric permille fields
--stream              Canonical engine stream; publishes one signal frame and
                      requires it for the associated per-task directives
--clear               Clear all directives

Exit codes:
  0 = success
  2 = scheduler not loaded
  6 = invalid PID
 10 = generation overflow
```

The kernel signal frame is a bounded native-endian map transport. It carries
values converted from the userspace prototype, but the BPF scheduler does not
verify the userspace HMAC or compute the predictor/controller/coordination
metrics itself. The bridge also refuses adaptive directives for current
`SCHED_FIFO`, `SCHED_RR`, and `SCHED_DEADLINE` targets; full kernel RT
coexistence remains unimplemented.

---

## 5. Metrics Schema (v2 → v7)

| Version | Columns | Added |
|---------|---------|-------|
| v2 | 40 | S1-S4, Q (geometric mean) |
| v3 | 66 | S2_effective, S3_conditioned |
| v4 | 83 | S4_burst, oscillation penalty |
| v5 | 107 | Controller state diagnostics |
| v6 | 120 | Policy mode, generation, persistence |
| v7 | 121 | Conditioned coordination semantics and canonical burst-sensitive S4 |

AC: Q = (S1 × S2 × S3 × S4)^(1/4)

v6 and v7 are append-only userspace contracts. v7 retains the v6 prefix,
requires `coordination_semantics_version=7`, uses `S3_conditioned` as the
canonical S3 value, and defines canonical `S4` as the minimum of historical
temporal stability and `S4_burst`. These are data-pipeline semantics, not
evidence of kernel scheduler ownership or performance.

---

## 6. Controller States

| State | RUN | YIELD | MIGRATE | THROTTLE | SLEEP |
|-------|-----|-------|---------|----------|-------|
| NORMAL | ✓ | ✓ | ✓ | ✓ | ✓ |
| DEGRADED | ✓ | ✓ | ✗ | ✓ | ✗ |
| SATURATED | ✓ | ✗ | ✗ | ✗ | ✗ |
| DISABLED | RUN only | ✗ | ✗ | ✗ | ✗ |

---

## 7. Research Governance

See [AGENTS.md](AGENTS.md) for work-package scope, invariants, claim classes, and development protocol.

See [docs/adr/](docs/adr/) for all 12 Architecture Decision Records.

---

## 8. Key Hashes

VirtualBox / release artifacts:

| File | SHA-256 |
|------|---------|
| Userspace source | `5fc21224846a2a17db0f02ce02efe8ebbe1067e40b0ad78e82419839d73657b9` |
| Userspace binary | `3a68b633e29e9d91060fa9bba0305940f02d04678573da115796f23850383e03` |
| Bridge contract | `08eaa93725f98331edffa67d3255b25bebcb589e8299401c40a089dc70007c97` |
| Kernel bzImage (6.12.96 VBox; NVMe off) | `d3d50d26b3d1a91196318a2c99d1c71a859c3171b69276bd26414ae6dfa9e912` |
| Kernel BTF (that bzImage) | `7af6be54b981c04e7e57c2043f3cb0247e05e564ff65271138197fd8a91ca458` |

This Kali 7.0.12 host (2026-08-14):

| File | SHA-256 |
|------|---------|
| Running BTF vmlinux | `3f39484930b332629a5864a1a703b0a39320cc1584f6e8a00dfbc6375b58ec76` |
| 7.0-ported BPF object | `ba82987fb2aa09d1746c7dbc1937830965182612c23377fd61c3ee75fc38dab4` |
