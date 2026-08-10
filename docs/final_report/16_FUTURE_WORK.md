# 16. Future Work (Stage 10+)

## Production Hardening
- Privilege drop after scheduler attach (capset)
- Symlink-safe file handling (O_NOFOLLOW)
- World-readable map prevention (umask enforcement)
- Audit logging for security events

## NUMA Validation
- Multi-node NUMA testing on physical x86_64 hardware
- Topology-aware CPU selection (distance-based)
- Cross-node migration measurement

## Scalability
- 8, 16, 32, 64 worker scaling on bare metal
- Perf-based profiling of BPF hot paths
- Bridge latency optimization (reduce read-back overhead)
- Map batching for multi-directive publication

## Reliability
- 1-hour + 24-hour soak tests
- Memory leak detection (valgrind, kmemleak)
- Counter overflow stress (UINT64_MAX boundary)
- Repeated fault injection (100+ cycles)

## Benchmarking
- Bare-metal CFS vs scx_simple vs ORCHESTRA comparison
- Phoronix Test Suite integration
- Statistical significance analysis (t-test, confidence intervals)
- P95/P99 tail latency measurements

## Research Extensions
- Academic paper submission
- Conference presentation
- Open-source release announcement
- Community contribution guidelines

## Architecture Extensions
- Multi-node distributed signal bus
- NUMA-aware placement optimization
- Energy-aware scheduling
- Thermal-aware throttling
- Deadline-aware action selection
