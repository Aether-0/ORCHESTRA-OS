# 9. Policy Engine

## Overview
The ORCHESTRA policy engine manages per-process Q-tables using tabular reinforcement learning with three lifecycle modes.

## Learning Algorithm
- **Algorithm:** Tabular Q-learning
- **State space:** 5 CPU × 2 memory × 3 thermal = 30 buckets
- **Action space:** 5 canonical actions
- **Q-table size:** 150 entries (30 states × 5 actions)
- **Learning rate:** α = 0.20
- **Discount factor:** γ = 0.90
- **Exploration:** ε-greedy, annealed from 0.30 → 0.02 (decay=0.998/tick)

## Reward Function
```
local_reward = +0.6 if action matches directive, -0.6 otherwise
difference_reward = w × n × (global_utility - counterfactual_utility)
  where w = 0.30, n = eligible workers
thermal_penalty = -0.40 if thermal > 0.90 and action == RUN
switch_penalty = frame.switch_penalty if action changed
final_reward = (1 - w) × local + w × difference + penalties
```

## Lifecycle Modes

### TRAIN
- Exploration enabled (ε-greedy)
- Q-table updates applied
- Consensus learning enabled
- Policy generation increments

### ADAPT
- Exploration disabled (greedy selection)
- Q-table updates only in NORMAL controller state
- Consensus enabled
- Bounded update delta

### EVALUATE
- Exploration disabled
- Q-table frozen (no updates)
- Consensus suppressed
- Policy generation frozen
- Reproducible decisions (same policy + seed = same action)

## Policy File Format

```
Offset  Size  Field
0       4     magic (0x504f4c59 = "POLY")
4       4     format_version (1)
8       4     schema_version (1)
12      4     header_length (64)
16      4     payload_length
20      4     state_count (30)
24      4     action_count (5)
28      8     policy_generation
36      8     train_update_count
44      8     adapt_update_count
52      12    padding
64      1200  Q-table (30×5×8 bytes, binary64)
1264    32    SHA-256 digest
```

## Atomic Save Procedure
1. Serialize to temporary file (`.tmp.<pid>`)
2. Flush and close
3. Reopen and validate temporary file
4. Rename atomically over destination
5. On failure: remove temporary, preserve previous policy

## Load Validation
Rejects: wrong magic, wrong version, wrong schema, wrong state count, wrong action count, oversized payload, truncated header, trailing bytes, non-finite Q values, digest mismatch
