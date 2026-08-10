# ORCHESTRA-OS

Predictive, cryptographically protected, hierarchical, signal-coordinated scheduling architecture for Linux.

**Status:** Research prototype — 9 stages validated, exact kernel boot achieved, real-machine benchmarks ready.

---

## Quick Links

| What | Link |
|------|------|
| **USB Deployment Kit** (everything for real machine) | [orchestra-usb-final.zip](./orchestra-usb-final.zip) |
| **Final Report** (Markdown + Mermaid flowcharts) | [ORCHESTRA-OS-Final-Report.md](./ORCHESTRA-OS-Final-Report.md) |
| **Final Report** (PDF) | [ORCHESTRA-OS-Final-Report.pdf](./ORCHESTRA-OS-Final-Report.pdf) |
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
│   ├── orchestra_paper_cpu.c       Main implementation (3384 lines)
│   ├── Makefile                    Build
│   └── README.md                   Usage
│
├── kernel/sched_ext/               Linux sched_ext kernel scheduler
│   ├── orchestra_scx_stage7.bpf.c  BPF scheduler (5 actions)
│   ├── orchestra_scx.bpf.c         Stage 6 minimal scheduler
│   ├── include/
│   │   ├── orchestra_bridge_v1.h   Bridge contract (versioned structs)
│   │   └── orchestra_scx.h         Scheduler types
│   ├── bridge/
│   │   └── orchestra_bridge.c      Userspace bridge CLI
│   └── scripts/
│       ├── check_kernel_config.sh  Verify CONFIG_SCHED_CLASS_EXT
│       ├── reproduce_stage7_runtime.sh  Stage 7 reproduction
│       └── stage8_validate.sh      Stage 8 full validation
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
│   ├── unit/                       25 named unit tests (GCC + Clang)
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
├── experiments/                    JSON manifests + metric schemas (v2-v6)
├── tools/                          Benchmark runner, PDF report generator
│
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

**Expected:** 25/25 unit tests, 34/34 validator tests, 5/5 integration scenarios, 0 Clang analyzer findings.

### Run the userspace demo

```bash
./orchestra_paper_cpu_demo/orchestra_paper_cpu \
  --workers 4 --duration 10 --mode orchestra --seed 42
```

---

## 2. Real-Machine Kernel Setup

### Prerequisites
- Linux 6.12+ with `CONFIG_SCHED_CLASS_EXT=y` and `CONFIG_DEBUG_INFO_BTF=y`
- `gcc`, `clang`, `make`, `bpftool`, `libbpf-devel`
- Root access

### Quick Install from USB

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

### Build BPF from source

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

### Build Bridge CLI

```bash
cc -O2 -Wall -Wextra -I kernel/sched_ext/include \
  kernel/sched_ext/bridge/orchestra_bridge.c \
  -o bridge -lbpf
```

### Load / Unload

```bash
# Load
sudo bpftool struct_ops register orchestra_scx_stage7.bpf.o /sys/fs/bpf/orch
cat /sys/kernel/sched_ext/state   # Should show "enabled"

# Pin maps
for m in bridge_control_ bridge_directiv bridge_telemetr bridge_task_map; do
  ID=$(sudo bpftool map list | grep -m1 "name $m" | awk '{print $1}' | tr -d ':')
  sudo bpftool map pin id $ID /sys/fs/bpf/$m
done

# Use bridge
sudo ./bridge --status
sudo ./bridge --publish --action RUN --target-pid <PID>

# Unload
sudo rm -rf /sys/fs/bpf/*
```

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

### Expected Overhead

| Scheduler | Relative to CFS |
|-----------|----------------|
| CFS | 1.00× (baseline) |
| scx_simple | ~1.02× |
| ORCHESTRA | ~1.20× |

ORCHESTRA's overhead comes from BPF callbacks, bridge maps, identity checks, controller gating, and telemetry counters.

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
  --dry-run            Validate without mutation
--clear               Clear all directives

Exit codes:
  0 = success
  2 = scheduler not loaded
  6 = invalid PID
 10 = generation overflow
```

---

## 5. Metrics Schema (v2 → v6)

| Version | Columns | Added |
|---------|---------|-------|
| v2 | 40 | S1-S4, Q (geometric mean) |
| v3 | 66 | S2_effective, S3_conditioned |
| v4 | 83 | S4_burst, oscillation penalty |
| v5 | 107 | Controller state diagnostics |
| v6 | 120 | Policy mode, generation, persistence |

AC: Q = (S1 × S2 × S3 × S4)^(1/4)

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

| File | SHA-256 |
|------|---------|
| Userspace source | `5fc21224846a2a17db0f02ce02efe8ebbe1067e40b0ad78e82419839d73657b9` |
| Userspace binary | `3a68b633e29e9d91060fa9bba0305940f02d04678573da115796f23850383e03` |
| Bridge contract | `08eaa93725f98331edffa67d3255b25bebcb589e8299401c40a089dc70007c97` |
| Kernel bzImage | `d3d50d26b3d1a91196318a2c99d1c71a859c3171b69276bd26414ae6dfa9e912` |
| Kernel BTF | `7af6be54b981c04e7e57c2043f3cb0247e05e564ff65271138197fd8a91ca458` |
