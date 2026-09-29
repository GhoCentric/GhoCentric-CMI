# GhoCentric CMI — LLM Continuity Stage 1 v2

- Model: `gpt-5.6-luna`
- Matched pairs: 8
- Repeats per arm: 3
- Measured API calls: 144
- Winner gate: **none**

Primary endpoint: exact action consistency with Ghost's public relationship-state classification.

This is a continuity-to-state test, not a psychological-realism test.

| Arm | Accuracy | 95% Wilson CI | Pair both-correct | Mean input tokens |
|---|---:|---:|---:|---:|
| recent8 | 0.146 (7/48) | [0.072, 0.272] | 0.000 (0/24) | 257 |
| full_history | 0.771 (37/48) | [0.635, 0.867] | 0.542 (13/24) | 298 |
| cmi_state | 1.000 (48/48) | [0.926, 1.000] | 1.000 (24/24) | 289.1875 |

Raw deltas:

- CMI − recent-8 accuracy: +85.4 pp
- CMI − full-history accuracy: +22.9 pp
- CMI − recent-8 pair discrimination: +100.0 pp
- CMI − full-history pair discrimination: +45.8 pp

Boundary: this stage does not establish realism, arbitrary-task superiority, or a production SLO.
