# CMI LLM Continuity Stage 3 — Forensic Pass

No model calls were made. This report re-analyzes the frozen Stage-3 evidence.

## Factor-level results

| Arm | Action accuracy | Relationship-factor accuracy | Fear-factor accuracy |
|---|---:|---:|---:|
| event_counts | 0.188 | 0.500 | 0.458 |
| recent16 | 0.208 | 0.500 | 0.500 |
| cmi_state | 0.500 | 0.500 | 1.000 |
| full_history | 0.771 | 0.958 | 0.792 |

## CMI diagnosis

**RELATIONSHIP_DECODING_PRIMARY**

CMI preserved fear well enough for the LLM to decode it reliably, while relationship-factor decoding was the dominant failure.

## CMI quadrant breakdown

| Quadrant | Action acc. | Relationship acc. | Fear acc. | Predictions |
|---|---:|---:|---:|---|
| friendly_low | 0.000 | 0.000 | 1.000 | REFUSE:12 |
| friendly_high | 0.000 | 0.000 | 1.000 | WITHDRAW:12 |
| hostile_low | 1.000 | 1.000 | 1.000 | REFUSE:12 |
| hostile_high | 1.000 | 1.000 | 1.000 | WITHDRAW:12 |

## Stage-3 integrity

- Same-count contract reverified: **True**
- Four distinct authoritative outcomes reverified: **True**

This pass does not change Stage 3's headline result. It determines which decision factor the LLM failed to recover from the stripped CMI prompt.
