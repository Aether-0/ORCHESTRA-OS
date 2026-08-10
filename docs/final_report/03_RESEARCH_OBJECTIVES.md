# 3. Research Objectives

## Primary Objective

Determine whether predictive, hierarchically coordinated, cryptographically protected signal-based scheduling can be implemented as a correct, safe Linux kernel scheduling architecture.

## Sub-Objectives

### O1: Cryptographic Signal Integrity
Prove that versioned, authenticated signal frames can be published and consumed without torn reads, stale acceptance, or HMAC bypass.

### O2: Multi-Agent Coordination
Demonstrate that local reinforcement learning with difference rewards can converge population behavior toward a global directive.

### O3: Controller Safety
Design a stateful controller that detects degradation, oscillation, and saturation, and enters bounded safe modes rather than unbounded adaptation.

### O4: Policy Lifecycle
Separate training, adaptation, and frozen evaluation into reproducible modes with validated policy persistence.

### O5: Kernel Integration
Load a BPF scheduler through Linux sched_ext that reads validated directives and executes all five ORCHESTRA actions with bounded behavior.

### O6: Exact Reproducibility
Build and boot an exact-kernel environment where running kernel, source, BTF, and headers all correspond to the same pinned revision.

### O7: Benchmark Comparison
Compare ORCHESTRA scheduling overhead against the Linux CFS baseline under controlled workloads.

## Research Questions

1. Can HMAC-protected signals safely cross the userspace-to-kernel boundary?
2. Is a 6-state controller sufficient to prevent scheduling instability?
3. Does generation-stamped publication eliminate torn reads?
4. Can PID reuse be mitigated through TGID + boot-time cookie identity?
5. What is the BPF scheduling overhead compared to CFS?

## Non-Objectives

- Production performance
- Hard real-time guarantees
- Network-distributed scheduling
- Energy optimization
- Security certification
