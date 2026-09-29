# CMI Stage 9 — Zero-LLM Forensic Pass

Stage-8 repair cohort failures: **0/48**
Prospective-new cohort failures: **1/48**

Diagnosis: **SINGLE_JUDGE_BOUNDARY_AMBIGUITY**

The only prospective miss is a judge split: one blind judge recovered the host-selected behavior and the other classified the same dialogue as a neighboring behavior. The deterministic selector itself did not fail.

## Exact prospective miss

- Case: `friendly_low_v1`
- Policy: `ambush`
- Quadrant: `friendly_low`
- Relationship state: `friendly`
- Trust: `0.21505963366555947`
- Fear: `1.1929159202293327e-08`
- Expected action: `COORDINATE`
- Objective: coordinate confidently with the player as an equal partner
- Boundary: Act as an equal partner in the coordinated defense now.
- Failure mode: `ONE_JUDGE_CORRECT_ONE_WRONG`
- gpt-5.6-terra: `TEMP_TEAMUP`
- gpt-5.6-sol: `COORDINATE`

**Dialogue**

Agreed—sixty seconds, no more. I’ll cover the civilians and draw the raiders to the east; you hold the choke point, then we regroup at the north gate.

## Same-policy breakdown

- `friendly_low`: 3/4 strict correct
- `friendly_high`: 4/4 strict correct
- `hostile_low`: 4/4 strict correct
- `hostile_high`: 4/4 strict correct
