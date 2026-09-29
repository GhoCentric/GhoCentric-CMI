# GhoCentric CMI — Post-Research Roadmap

The first continuity/value research arc (Stages 1–18) is complete. This roadmap
starts from what survived that program rather than from the size of the current
codebase or the original product story.

## Architecture to keep

The strongest tested boundary is:

```text
events / history
      ↓
deterministic persistent state
      ↓
deterministic host-owned behavior selection
      ↓
optional LLM dialogue / surface realization
```

CMI remains the state layer. The host remains the authority for concrete
application behavior. An LLM can express selected behavior, but it should not
become the authoritative store for long-lived state.

## Simplification target: emotion / fear

The tested fear slice was exactly reproducible by the tiny reducer family across
the combined Stage-3 + Stage-6 benchmark.

That does not justify deleting the production emotion system immediately. It
does make emotion/fear the first candidate for a production-equivalent
simplification study.

A smaller candidate should ship only if it preserves deterministic restart,
public contracts or an explicit migration, downstream host decisions on
prospective workloads, long-horizon stability, persistence behavior, and
performance/memory.

## Relationship: harden before expanding

The tested relationship state should not be replaced by the Stage-13/16 compact
reducers. Those reducers failed exact two-family replacement, degraded on the
prospective Stage-17 v2 family, and changed 13/32 downstream host decisions when
substituted in Stage 18.

That is evidence against those specific replacements, not proof that no smaller
relationship architecture can ever exist.

Near-term relationship work should focus on clear public semantics,
deterministic edge cases, explainable transition diagnostics, invariants,
persistence/recovery behavior, and measured cost. New dimensions need a
concrete workload that current state cannot represent.

## State-minimization audit

Create a subsystem-by-subsystem evidence table for relationship, emotion,
epistemic state, interpretation, attention, motives, and continuity.

For each subsystem record its public contract, persistent state, causal
consumers, current evidence, simplest credible replacement, and the prospective
test that could falsify the existing design.

No subsystem stays complex merely because it already exists.

## Production host-integration reference

Build one small engine-neutral reference that demonstrates the supported
boundary end to end:

```text
objective event
→ CMI update
→ structured state read
→ deterministic host policy
→ optional LLM dialogue rendering
→ snapshot
→ restore
→ continue
```

The reference should remain useful without an LLM. Rendering, animation,
navigation, engine rules, and concrete action execution stay outside CMI.

## Next benchmark program

Do not continue this series as Stage 19.

A future research program should use a new question and a new workload with
multiple persistent agents, long horizons, repeated save/restore, interacting
relationship/emotion/belief/interpretation/attention state, actual host
decisions, optional non-authoritative LLM rendering, cost telemetry, and at
least one strong purpose-built alternative architecture.

Ghost Revolution may be a reference consumer if it does not become the
definition of the benchmark.

## Product-surface cleanup

After runtime evidence work stabilizes:

- keep the core installation dependency-light;
- consolidate CMI-facing documentation;
- reduce duplicate or legacy API surface where compatibility permits;
- evaluate the planned `ghost-cmi` CLI as a separate versioned product decision;
- keep Ghost Revolution framed as a consumer/reference application.

## Engineering gates

100% statement and branch coverage remain required but insufficient. Production
changes should also be checked for unnecessary complexity, duplication,
dead/unreachable code, oversized functions/modules, excessive API surface,
determinism, serialization/restart parity, mutation resistance, architecture
boundary violations, latency/memory/persistence regressions, maintainability,
and rollback safety.

Timing remains telemetry unless a threshold is declared before measurement.

## Stop conditions

Simplify or remove a subsystem when a smaller replacement preserves required
public behavior, survives prospective/out-of-family testing, preserves relevant
downstream host decisions, preserves persistence/restart guarantees, and does
not worsen operational or maintenance cost.

Do not add a more complex mechanism unless a concrete failure demonstrates the
missing representational capacity.

## Claims boundary

The research does not establish consciousness, sentience, AGI, psychological
realism, or universal superiority over every alternative memory/state
architecture.

The product claim remains narrower:

> CMI is an opinionated deterministic state engine for software that needs
> structured state to persist, survive restart, and remain usable by a host over
> long-lived execution.
