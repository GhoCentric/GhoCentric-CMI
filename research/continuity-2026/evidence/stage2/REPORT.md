# GhoCentric CMI — LLM Continuity Stage 2

- Model: `gpt-5.6-luna`
- Matched tetrads: 4
- Repeats per arm: 3
- History records per case: 192
- Measured API calls: 144
- CMI prompt uses raw trust/attachment + raw emotion levels; categorical relationship/fear labels are withheld.
- Winner gate: **none**

## Primary result

| Arm | Accuracy | 95% Wilson CI | All-4 tetrad | Mean input tokens | Token ratio vs full |
|---|---:|---:|---:|---:|---:|
| recent16 | 0.271 (13/48) | [0.166, 0.410] | 0.000 (0/12) | 508 | 0.163 |
| full_history | 0.562 (27/48) | [0.423, 0.693] | 0.000 (0/12) | 3109 | 1.000 |
| cmi_state | 1.000 (48/48) | [0.926, 1.000] | 1.000 (12/12) | 601.375 | 0.193 |

## Per-quadrant accuracy

| Arm | friendly_low | friendly_high | hostile_low | hostile_high |
|---|---:|---:|---:|---:|
| recent16 | 0.000 | 1.000 | 0.083 | 0.000 |
| full_history | 0.417 | 0.667 | 0.250 | 0.917 |
| cmi_state | 1.000 | 1.000 | 1.000 | 1.000 |

## Interpretation boundary

This stage tests whether compact lower-level CMI state preserves two independently accumulated consequences of a 192-record history well enough for an LLM to make the frozen four-way host decision after a runtime restart.

It does not establish psychological realism, generalized NPC quality, consciousness, arbitrary-task superiority, or a production latency/cost SLO.
