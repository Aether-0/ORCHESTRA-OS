# 8. Controller Evolution

## Stage 1-3: Memoryless Controller
- Single-actuator PID adjusting predictor gain
- No state tracking
- No hysteresis
- No saturation detection

## Stage 4: Safety State Machine
- 6 explicit states with validated transitions
- Rolling-window metrics (10 samples) + actuator oscillation (8 samples)
- Hysteresis: entry/exit thresholds differ, minimum residence time enforced
- Saturation: actuator at bound + metric deficit persists → SATURATED
- Oscillation: 4+ sign reversals → DISABLED
- Last-Known-Good: only promoted in stable NORMAL (5+ updates)

## Stage 5: Policy Mode Gating
- Controller state gates policy updates
- DISABLED → no Q-table mutations
- ROLLBACK → last-known-good restoration
- RECOVERY → conservative adaptation only

## Stage 7: BPF Gating
- Controller state propagated to kernel via bridge control map
- BPF `bridge_ctrl_allowed()` enforces action restrictions
- 6×5 matrix (30 cells) tested

## State Transition Diagram

```
NORMAL ──(avg S3/S4 < 0.82)──→ DEGRADED
NORMAL ──(persistent saturation)──→ SATURATED
NORMAL ──(critical fault)──→ DISABLED

DEGRADED ──(recovered metrics)──→ NORMAL
DEGRADED ──(persistent saturation)──→ SATURATED
DEGRADED ──(oscillation)──→ DISABLED

SATURATED ──(recovered)──→ NORMAL
SATURATED ──(timeout)──→ ROLLBACK

ROLLBACK ──→ RECOVERY (automatic)

RECOVERY ──(stable metrics)──→ NORMAL
RECOVERY ──(failure)──→ DISABLED

DISABLED ──→ RECOVERY (controlled)
```
