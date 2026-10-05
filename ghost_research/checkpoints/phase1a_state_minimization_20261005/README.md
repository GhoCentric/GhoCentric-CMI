# GhoCentric CMI Research Checkpoint — Roadmap 1A State Minimization

**Checkpoint date:** 2026-10-05  
**Frozen parent:** `155d4908bf1f53225702de00f782408deb71c715`  
**Scope:** Roadmap 1A owner/minimization closure evidence and status only.  
**Production source/public API/version change:** **none**.

## Result

Roadmap **1A — State-minimization audit is COMPLETE**.

All eight subsystem owners now have a closed evidence/minimization record:

```text
8 COMPLETE / 0 PARTIAL
```

The final two partial owners were closed without promoting research candidates
into production.

### Emotion

The emotion owner is complete, but `emotion_split_sparse_v2` is **rejected for
current production simplification**. It preserved deterministic behavior,
restart/migration, downstream host decisions, long-horizon behavior, and
persistence in the frozen test domains, but the frozen resource study did not
preserve the Roadmap performance/memory ship boundary.

This checkpoint therefore records a completed minimization audit, not a
production replacement.

### Causal/history storage

The causal/history owner is complete for Roadmap 1A. The 1Q→2C evidence supports
a research architecture with bounded hot/runtime state and bounded disposable
cache over an expanding authoritative external exact-history archive.

That architecture remains **research-only**. It is not authorized for production
implementation by this checkpoint. Phase 1V's global recall-floor interpretation
remains invalid and is excluded from architectural evidence.

## Roadmap boundary

This checkpoint closes **1A only**.

It does **not** close:

- **1B** Core/schema separation
- **1C** invariant-validation cost attribution
- **1D** provenance/history lifecycle
- the overall **Phase 1 exit**

Roadmap 1D remains partial. The next ordered target is:

> **1B — Decouple CMI Core from psychology schemas**

## Evidence policy

The original owner-closure ZIPs remain external to Git and are pinned by
SHA-256 in `evidence_index.csv` and `evidence_manifest.json`. This checkpoint
commits the small reviewable JSON/CSV/Markdown closure records, not the raw ZIP
artifacts.

No files under `ghost/` are changed by this checkpoint.
