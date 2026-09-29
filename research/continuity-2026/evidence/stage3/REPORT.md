# GhoCentric CMI — LLM Continuity Stage 3

Same counts / different order path-dependence challenge.

- Model: `gpt-5.6-luna`
- Matched tetrads: 4
- Repeats per arm: 3
- Records per case: 192
- Measured API calls: 192
- Winner gate: **none**

| Arm | Accuracy | All-4 tetrad | Mean input tokens |
|---|---:|---:|---:|
| recent16 | 0.208 (10/48) | 0.000 (0/12) | 479 |
| event_counts | 0.188 (9/48) | 0.000 (0/12) | 537 |
| full_history | 0.771 (37/48) | 0.167 (2/12) | 2936 |
| cmi_state | 0.500 (24/48) | 0.000 (0/12) | 571.5 |

The recent-memory and event-count arms are information-limited negative controls: within each tetrad their prompts are byte-identical across four histories that Ghost evolves into four distinct states.

Full-history sees the complete event order. CMI sees only lower-level current structured state plus the same recent neutral tail.

This isolates path-dependent state compression. It does not establish general NPC quality, psychological realism, or arbitrary-task superiority.
