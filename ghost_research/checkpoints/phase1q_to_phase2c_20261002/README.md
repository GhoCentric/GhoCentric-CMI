# GhoCentric CMI Research Checkpoint — Phase 1Q through Phase 2C

**Checkpoint date:** 2026-10-02
**Frozen production/source parent:** `37e80da4bf081ff01d176fb446534754bc465533`
**Scope:** research evidence and architecture conclusions only.
**Production source/public API/version change in this checkpoint:** **none**.

This checkpoint preserves the evidence chain that moved the memory architecture from an
unbounded exact-history problem to a bounded-runtime / external-authoritative-history design.
It deliberately does **not** promote the research implementation into `ghost/`.

## What the evidence establishes

- **Phase 1Q:** current causal episode history is append-only by default; explicit capacity is
  backpressure, not a retention policy.
- **Phase 1R:** no tested candidate could preserve the current exact historical-recall contract
  in bounded internal storage.
- **Phase 1S:** the lifecycle gap was isolated to historical recall rather than live continuity.
- **Phase 1T / 1U:** adaptive retention showed useful signal on one workload, then failed to
  justify itself under a more adversarial distribution.
- **Phase 1V:** the original capacity result is retained for provenance but its global recall-floor
  interpretation is invalid and must **not** be used as architectural evidence.
- **Phase 1W:** corrected per-episode exact-vs-matched-generic counterfactuals established that
  only a subset of historical payloads materially change future behavior on that workload.
- **Phase 1X:** a research-only hybrid full-payload/stub representation reproduced production
  behavior exactly, but exact stubs still implied growth.
- **Phase 1Y:** a creation-time selector reached the validated 128 tier on the controlled workload;
  this was explicitly controlled-only evidence.
- **Phase 1Z:** the frozen selector did not generalize sufficiently and, more importantly, the
  held-out workload required more than 128 full payloads even for the oracle.
- **Phase 2A:** the minimum number of records needed to preserve 95% of measured future exact-payload
  behavioral value scaled approximately linearly with both history length and valuable-memory
  density (`beta ~= 0.9935` and `beta ~= 0.9889` over the tested ranges).
- **Phase 2B:** with exact history externalized, local storage remained fixed at 128 full + 128 stubs,
  hot snapshot size remained fixed, and sampled routed recall remained exactly behaviorally equivalent
  through 16,384 external episodes.
- **Phase 2C:** the external exact archive became the authoritative memory owner; local full/stub state
  was treated as disposable cache. Promotion/demotion preserved 128 + 128 bounds, 14/14 real
  process-death failpoints recovered to exact OLD-before-COMMIT or exact NEW-after-COMMIT state,
  zero torn cache states were observed, and total cache loss rebuilt successfully with 3/3 exact
  post-rebuild recall probes. Stubs were not required for correctness.

## Current research architecture

1. **Hot continuity state** — bounded and immediately behaviorally active.
2. **Bounded local full-payload cache** — fast working set; non-authoritative.
3. **Bounded optional stub cache** — routing/cache hint only; not required for exact recall.
4. **Expanding authoritative external exact-history archive** — owns durable episode identity/payload.

The key separation is that **runtime continuity can remain bounded while autobiographical history grows**.

## What is *not* yet production-validated

- The external recall path still relies on a private Ghost helper in research harnesses.
- New-event ingestion ordering/atomicity across runtime + authoritative archive + cache is unresolved.
- Concurrent/multi-process cache mutation semantics are unresolved.
- Cache promotion/demotion policy is a research probe, not a production retention policy.
- External archive segmentation/compaction and very-long-horizon lifecycle remain to be adjudicated.
- A second genuinely different host/task replication is still required before production implementation.
- Phase 1V's invalid global-floor result must not be resurrected as evidence.

## Evidence policy

Original evidence ZIPs remain external to Git and are pinned here by SHA-256. This checkpoint
extracts small text/JSON/CSV evidence for review and records every ZIP member hash in
`evidence_manifest.json`; it intentionally does not commit binary ZIP/database artifacts.

The maintained regression and core branch-coverage gates used for this checkpoint are recorded
under `gates/`. The checkpoint commit itself is documentation/research evidence only.
