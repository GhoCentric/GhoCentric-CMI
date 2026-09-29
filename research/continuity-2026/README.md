# GhoCentric CMI — Continuity Research Arc (Stages 1–18)

This directory is the public research record for the first closed CMI continuity
experiment program.

The question was not “can CMI win a benchmark?” It was:

> **Does persistent deterministic state provide useful continuity for long-lived
> LLM/NPC systems, and how much architecture is actually required to get that
> value?**

The series deliberately includes negative results, failed assumptions, post-hoc
repairs, stronger baselines, simplification attacks, and prospective holdouts.

## Final result in plain language

CMI's core state/authority architecture survived the research program, but some
tested state dimensions were simpler than the full engine.

The tested fear dimension was completely reproducible by a tiny deterministic
reducer across the combined Stage-3/Stage-6 benchmark. The tested relationship
dimension was not. Three compact relationship alternatives failed exact
two-family replacement, then degraded to 75–78% agreement on a prospectively
generated third history family.

In the final composed test, CMI combined relationship, emotion,
interpretation, attention, continuity foreground, and snapshot/restart with
32/32 exact restart parity. Replacing only the live relationship state with the
frozen compact relationship approximation changed 13/32 deterministic host
decisions.

That does **not** prove psychological realism or universal superiority. It does
show that the frozen compact relationship approximation was not behaviorally
interchangeable with CMI in the tested composed pipeline.

## Stage summary

| Stage | Main result |
|---|---|
| 1 | CMI 48/48; full history 37/48; recent 7/48. Later analysis found the first contract too close to an answer key. |
| 2 | Two-dimensional relationship × fear state: CMI 48/48; full history 27/48. |
| 3 | Same counts/different order preserved distinct Ghost state, but raw CMI representation fell to 24/48. |
| 3B | Merely exposing the public relationship label did not repair the interface. |
| 3C | Explicit semantic contract repaired it: semantic CMI 48/48. |
| 4 | Same state reused across three host policies: 96/96. |
| 5 | Semantic action mapping reproduced on Terra and Sol in the tested contract. |
| 6 | New history shapes: semantic CMI 96/96; full history 27/96. |
| 7 | Natural dialogue: semantic 42/48 strict; full history 15/48. |
| 7B | Post-hoc renderer clarification recovered 48/48. |
| 8 | Held-out policies: semantic dialogue 41/48; full history 19/48. |
| 9 | Deterministic host selector + LLM renderer: 48/48 repair cohort, 47/48 prospective. |
| 10 | Remaining miss exposed COORDINATE/TEMP_TEAMUP evaluator ambiguity. |
| 11 | All 3 reverse-classification misses passed intent fidelity; 59/60 total passed. |
| 12 | Strong full-history LLM reducer: 25/80 joint CMI-state match; stable but systematically different. |
| 13 | Tiny deterministic reducer reproduced Stage-6 relationship + fear 16/16 LOOCV. |
| 14 | Frozen Stage-6 reducer collapsed out of family: 4/16 joint on Stage-3. |
| 15 | Universal tiny reducer: 30/32 joint; fear 32/32; relationship 30/32; zero perfect relationship parameterizations. |
| 16 | Three minimal relationship replacements all failed the exact capacity + LOOCV requirement. |
| 17 v1 | Invalid/incomplete generator: 768/768 hostile, aborted before baseline scoring. |
| 17 v2 | Prospective holdout: L0 25/32, L1 24/32, L2 25/32; no refitting. |
| 18 | 32/32 composed restart parity; compact relationship 16/32; host decisions diverged 13/32. |

## Architecture supported by the experiments

```text
events / history
      ↓
deterministic persistent state
      ↓
deterministic host-owned behavior selection
      ↓
LLM dialogue / surface realization
```

The LLM is useful for expression. It is not treated as the authoritative source
of long-lived application state or final game behavior.

## Evidence

`evidence/` contains public-safe copies of frozen evidence artifacts. The
publication deliberately excludes environment files, credentials, caches, and
unrelated downloads. Files over the publication size cap are omitted rather
than silently altered.

`EVIDENCE_MANIFEST.json` records the copied-file SHA-256 hashes.

Read `METHODOLOGY.md` and `LIMITATIONS.md` before generalizing these results.
