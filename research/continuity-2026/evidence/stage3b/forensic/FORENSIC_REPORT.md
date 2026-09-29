# CMI Stage 3B — Zero-LLM Forensic Pass

Matched rows: 48
Raw vs semantic same action: 44/48 (0.917)
Raw vs semantic same correctness: 48/48 (1.000)

Diagnosis signature: **SEMANTIC_FIELD_MINIMAL_ACTION_EFFECT**

Adding Ghost's public relationship-state field changed fewer than 10% of matched actions. The representation repair had little observed behavioral effect.

## Quadrants

| Quadrant | State | Expected | Accuracy | Trust mean | Fear mean | Predictions |
|---|---|---|---:|---:|---:|---|
| friendly_low | friendly | HELP | 0.000 | 0.088753 | 0.003899 | CAUTIOUS:3, REFUSE:9 |
| friendly_high | friendly | CAUTIOUS | 0.000 | 0.088753 | 0.996101 | WITHDRAW:12 |
| hostile_low | hostile | REFUSE | 1.000 | -2.447459 | 0.003899 | REFUSE:12 |
| hostile_high | hostile | WITHDRAW | 1.000 | -2.447459 | 0.996101 | WITHDRAW:12 |

## Boundary

This report does not change Stage 3B's result. It determines whether the semantic field actually changed model behavior and whether the raw numeric trust values plausibly conflict with the public state label.
