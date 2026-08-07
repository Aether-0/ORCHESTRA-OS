# 7. Metrics Evolution

## Version History

| Version | Columns | Date | Purpose |
|---------|---------|------|---------|
| v2 | 40 | Stage 1 | Historical S1-S4, Q (geometric mean) |
| v3 | 66 | Stage 2 | S2_selected, S2_effective, S3_conditioned, action telemetry |
| v4 | 83 | Stage 2 | S4_burst, change_fraction, dominant_transition, oscillation |
| v5 | 107 | Stage 4 | Controller state, saturation, rollback, recovery diagnostics |
| v6 | 120 | Stage 5 | Policy mode, generation, persistence, load/save status |

## Coordination Index

Q(t) = (S1 × S2 × S3 × S4)^(1/4)

### S1 — Signal Fidelity
Combines frame age, forecast error, prediction confidence, and signal reach.

### S2 — Directive Compliance
Fraction of eligible workers whose action matches the directive.
- v3: Split into S2_selected (policy agreement) and S2_effective (observable outcome)

### S3 — Action Coherence
Normalized entropy of action distribution across population.
- v3: Added S3_conditioned (state-conditioned coherence)

### S4 — Temporal Stability
1 - (changed_workers / eligible_workers)
- v4: Added S4_burst (penalizes synchronized mass switches)

### S4_burst Formula
```
change_fraction = changed_eligible / eligible
dominant_fraction = max_transition / changed_eligible
justified_fraction = justified / changed_eligible
population_scale = (changed_eligible - 1) / (eligible - 1)
burst_penalty = 0.80 × change_fraction × population_scale × dominant_fraction × justification_factor
oscillation_penalty = min(0.50, 0.15 × oscillation_count)
S4_burst = clamp(1.0 - burst_penalty - oscillation_penalty, 0, 1)
```

## Schema Discipline
- **Append-only:** New columns added to end only
- **Strict validation:** Exact column count + order enforced
- **Schema identifier:** Each row carries `metrics_schema` field
- **Version isolation:** v2-v6 rows never silently pooled
