# VBox MCP Full Test Ladder Summary

**Claim class:** VirtualBox userspace / kernel-prototyped (not bare-metal)

**Guest:** orchestra-scx-lab (Fedora 40, kernel 6.12.96, 4 vCPU / 8 GB)  
**BTF SHA-256:** `7af6be54b981c04e7e57c2043f3cb0247e05e564ff65271138197fd8a91ca458`  
**Host commit (synced tree):** `30b01aa51ced364b0b4e367dc5a1e4582cddaa51`  
**Date:** 2026-08-13

## MCP / transport notes

- `vagrant-mcp` `ensure_dev_vm` / `exec_command` / `snapshot_save` failed: Vagrant 2.3.7 does not support VirtualBox 7.2.
- VM revived with `VBoxManage startvm --type headless`.
- Guest execution via SSH (`vagrant@127.0.0.1:2222`, insecure private key).
- Snapshots via `VBoxManage snapshot` (`pre-full-test`, `pre-bpf-load`, `pre-stage8`).

## Phase results

| Phase | Result | Notes |
|-------|--------|-------|
| A make check/unit/integration | **PASS** | Unit 25/25 + validators; integration EXIT=0 including MAP_SHARED + 34 CSV validator tests |
| B demo smoke | **PASS** | paper_cpu 10s orchestra seed 42 |
| B signal microbenchmark | **PASS** | 12/12 validated |
| B paper_cpu harness (v2/v5 manifests) | **FAIL (schema)** | Binary emits metrics/v6; manifests expect v2/v5. Runtime OK; validation rejected headers |
| C sanity + BPF build/load gate | **PASS** | CONFIG_SCHED_CLASS_EXT/BTF OK; load/unload/reload enabled→disabled |
| D stress (stock scripts) | **PARTIAL** | CPU stress CFS 60s + ORCHESTRA 120s PASS; memory `dd` left multi-GB files; suite aborted early (`set -e` / disk) |
| D stress/bench/compare (fixed harness) | **PASS** | Avoided `jobs -p` wait-on-scx_simple hang; CPU+I/O stress; CFS/scx/orchestra benches |
| E stage8 multicore + 30-min stability | **PASS** | 1802s stability, state=enabled, no panics; mem ~383–393 MB |
| E stage8 fault injection (script) | **PARTIAL** | Script exited on invalid-PID under `set -e`; faults completed manually (invalid PID rc=6 rejected) |
| E stage9 compare (fixed) | **PASS** | CFS / scx_simple / ORCHESTRA cpu+mixed |

## Selected measurements (VirtualBox only)

### Phase D fixed benchmark (elapsed ~30s fixed-duration busy loops)

| Scheduler | 1w ms | 2w ms | 4w ms | Notes |
|-----------|-------|-------|-------|-------|
| CFS | 29533 | 29997 | 29998 | baseline |
| scx_simple | 29733 | 29995 | 29996 | |
| ORCHESTRA | 29410 | 29996 | 29998 | higher cumulative ctxt vs CFS |

Wall-clock is not a throughput discriminator for fixed-duration spins; context-switch counters rose under ORCHESTRA (see CSVs).

### Stage 9 CPU (4 workers × 30s)

| Scheduler | elapsed_ms | ctx |
|-----------|------------|-----|
| CFS | 29991 | 17844721 |
| scx_simple | 29747 | 18624312 |
| ORCHESTRA | 29447 | 19502095 |

## Known script defects discovered

1. `benchmark_suite.sh` / similar: `wait $(jobs -p)` waits forever on background `scx_simple`.
2. `stress_suite.sh` memory fallback writes multi-GB `/tmp/orchestra-stress-*` files.
3. `stage8_validate.sh`: `set -e` aborts fault injection when invalid PID returns non-zero.
4. Multicore bench uses invalid C `volatile` in bash (`volatile: command not found`); workers still ran via `:` loop path partially; dispatch counts collected.

## Artifacts

Under `artifacts/test-results/2026-08-13/vbox-mcp/{phase-a..phase-e}/`.
