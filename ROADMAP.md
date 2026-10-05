# GhoCentric CMI — Post-Research Infrastructure Roadmap

The first continuity/value research arc (Stages 1–18) is complete.

This roadmap starts from what survived that program rather than from the size of
the current codebase or the original product story.

The next question is no longer:

> Can CMI preserve continuity better than a weak memory baseline?

The next question is:

> What is the smallest, most general, production-credible continuity substrate
> that preserves the guarantees CMI has actually earned?

## North Star

CMI should mature into:

> **A domain-agnostic deterministic continuity substrate that preserves
> structured state across time, restart, software evolution, model replacement,
> and production runtime constraints while leaving final behavior under host
> control.**

The goal is not to prove CMI is universally necessary. The goal is to establish
where its guarantees justify adoption instead of a simpler state implementation.

The completed Stages 1–18 provide evidence primarily for:

```text
temporal continuity
restart continuity
deterministic host authority
```

The next program targets:

```text
version continuity
model continuity
operational continuity
domain portability
```

# Phase 1 — State Minimization + Core / Schema Separation

This is the immediate next phase.

## 1A. State-minimization audit

> **Status — COMPLETE (2026-10-05).**
>
> All eight subsystem owner/minimization records are closed. The emotion audit
> rejected the current `emotion_split_sparse_v2` production replacement on the
> frozen resource ship boundary despite semantic/persistence equivalence. The
> causal/history audit supports bounded runtime/cache state over an expanding
> authoritative external exact-history archive as a **research-only**
> architecture; it does not authorize production implementation.
>
> Evidence checkpoint:
> `ghost_research/checkpoints/phase1a_state_minimization_20261005/`.
>
> This closes **1A only**. Roadmap **1D remains partial**, the overall Phase 1
> exit is **not met**, and the next ordered target is **1B Core/schema
> separation**.

Audit every major subsystem:

```text
relationship
emotion
epistemic state
interpretation
attention
motives
continuity
causal/history storage
```

For each subsystem, document owned state, mutation inputs, causal consumers,
invariants, persistence footprint, restart requirements, current evidence, the
simplest credible replacement, and the prospective test that could falsify the
current design.

No subsystem remains complex merely because it already exists.

### First simplification target: emotion / fear

The tested fear slice was exactly reproducible by the tiny reducer family across
the combined Stage-3 + Stage-6 benchmark.

That does not justify deleting production emotion machinery immediately. It does
make emotion/fear the first candidate for a production-equivalent simplification
study.

A smaller implementation should ship only if it preserves deterministic state,
restart parity, public contracts or an explicit migration, downstream host
decisions, long-horizon stability, persistence compatibility, and performance /
memory.

### Relationship: harden before expanding

The tested relationship state should not be replaced by the Stage-13/16 compact
reducers.

Those reducers failed exact Stage-3 + Stage-6 replacement, degraded
prospectively on Stage-17 v2, and changed 13/32 downstream host decisions in
Stage 18.

That is evidence against those specific replacements, not proof that no smaller
relationship architecture can exist.

Near-term relationship work should focus on clearer public semantics,
deterministic edge cases, transition diagnostics, invariants, mutation
resistance, persistence/recovery behavior, and measured cost.

Do not add dimensions or parameters without a concrete workload that existing
state cannot represent.

## 1B. Decouple CMI Core from psychology schemas

CMI Core should become **schema-agnostic, but not semantics-free**.

The core should know how to manage:

```text
entity
typed state
event
transition
dependency
provenance
history
invariant
snapshot
migration
query
recovery
```

The core should not require concepts such as:

```text
fear
trust
betrayal
motive
attention
NPC
threat response
```

Those become first-party schemas/modules built on top of Core.

Conceptually:

```text
                    CMI CORE
                       │
        ┌──────────────┼──────────────┐
        │              │              │
 deterministic    persistence      schema /
 transitions       recovery        migration
        │              │              │
        └──────────────┼──────────────┘
                       │
                typed state graph
                       │
        ┌──────────────┼──────────────┐
        │              │              │
 psychology       DevOps / agent    custom host
 reference pack   schemas           schemas
```

CMI must not collapse into an unrestricted JSON container.

The opinions that have earned their place remain part of Core: determinism,
explicit mutation, bounded transitions, provenance, snapshotability, migration
rules, and host authority.

The existing psychology stack becomes the first sophisticated reference schema,
not the definition of the engine.

## 1C. Invariant-validation cost gate

Core/schema decoupling introduces a performance trap.

A generic Python validation layer must not recursively deep-inspect large nested
schemas on every mutation unless that cost is explicitly justified.

Phase 1 must separately measure:

```text
transition logic
schema/type validation
invariant validation
serialization
compression
index work
disk I/O
```

Fast-path validation should be bounded and proportional to the mutation wherever
practical.

A Phase-2 persistence benchmark is invalid if Python schema-validation overhead
is dominating the result and being blamed on storage.

## 1D. Provenance/history lifecycle

Provenance does not mean append forever.

Every schema needs an explicit retention model for:

```text
live causal state
hot provenance
bounded/relevant history
cold archival history
compaction
trimming
reconstruction guarantees
```

The live state graph must not grow without bound merely because execution
continues.

Long-run tests must measure hot rows/entries, cold rows/entries, live memory,
snapshot size, archive size, query cost, compaction cost, and retention
correctness.

This should reuse lessons from the compact/indexed epistemic and
continuity-storage work rather than rebuilding an infinitely growing hot graph.

## Phase 1 exit criteria

Phase 1 is complete only when:

1. CMI can be described without reference to NPC psychology.
2. The psychology system still fits cleanly as a first-party schema/module.
3. Every major subsystem has an evidence/minimization record.
4. Validation overhead is separately attributable.
5. Provenance/history growth has an explicit bounded lifecycle.
6. No production simplification is accepted without prospective equivalence evidence.

# Phase 2 — Production Persistence Lifecycle

The important requirement is not “use lock-free persistence.”

Lock-free code, WALs, ring buffers, background workers, and copy-on-write
snapshots are implementation options.

The requirement is:

> **Persistence must not impose unacceptable synchronous stalls on the host.**

## 2A. Attribute current persistence cost

Break measured persistence cost into mutation, snapshot construction,
canonicalization, schema/invariant validation, serialization, compression, index
construction/update, filesystem write, fsync/durability, and recovery metadata.

The previously observed integrated long-case latency must not automatically be
called a frame stall unless caller-blocking time is measured directly.

Record total operation time, caller-blocking time, p50/p95/p99/p99.9, maximum
stall, bytes per event, allocation pressure, queue depth, disk throughput, and
recovery time.

## 2B. Research asynchronous persistence architectures

Candidate designs may include:

```text
authoritative in-memory mutation
        ↓
append-only journal / WAL
        ↓
bounded queue
        ↓
background persistence worker
        ↓
checkpoint / compacted snapshot
```

Possible mechanisms include write-ahead logging, bounded ring buffers, batched
journals, copy-on-write snapshots, incremental checkpoints, and background
snapshot construction.

No mechanism is assumed correct before measurement.

## 2C. Define durability states

Async persistence requires an explicit durability contract.

For example:

```text
applied
queued
journaled
checkpointed
durable
```

Those states must not be conflated.

The engine must define behavior when disk is slow, the queue fills, the writer
falls behind, the process dies mid-checkpoint, storage becomes unavailable,
mutation outruns memory, or recovery sees a partial tail.

Backpressure must be bounded and observable.

## 2D. Host-loop / frame-budget benchmark

After the architecture exists, benchmark against predeclared host budgets.

Representative loops:

```text
30 Hz
60 Hz
120 Hz
service-loop latency budgets
```

Measure caller-visible stalls rather than only total batch duration.

## Phase 2 exit criteria

Thousands of mutations can be persisted and recovered while caller-visible
stalls remain within a predeclared budget, memory/backpressure stay bounded,
crash recovery is deterministic, durability state is explicit, and no state is
silently lost.

# Phase 3 — Schema Evolution + Deterministic Migration

Production software changes.

CMI must graduate from:

```text
snapshot vN
→ runtime vN
```

to:

```text
snapshot vN
→ deterministic migration
→ runtime vN+1
→ validated continuation
```

## 3A. Version schemas independently

Persisted modules should have explicit schema identities/versions for Core,
relationship, emotion, epistemic state, interpretation, attention, and custom
host schemas.

A developer should not need to migrate unrelated state because one module
changed.

## 3B. Deterministic migration graph

Support explicit migration edges such as:

```text
1.0 → 1.1
1.1 → 1.2
1.2 → 2.0
```

Each migration should provide pre-validation, deterministic transform,
post-validation, migration provenance, failure reason, and rollback/no-commit
semantics.

No silent schema inference.

## 3C. Test hostile migration cases

Include renamed fields, deleted fields, new required fields, split/merged
fields, enum changes, bound changes, graph-topology changes, module
addition/removal, partially corrupted snapshots, and unknown future schema
versions.

## 3D. Fleet-scale migration

Validate migration across 10, 100, 1,000, and 10,000+ persisted states.

Measure success/failure counts, throughput, peak memory, storage amplification,
rollback behavior, and deterministic output hashes.

## Phase 3 exit criteria

A frozen old-state corpus can be upgraded deterministically and safely to a new
runtime, including explicit failure handling and bulk migration.

# Phase 4 — `ghost-bench`: Reproducible External Benchmarking

The current research archive is evidence, but outsiders should not need to
reverse-engineer dozens of evidence files to reproduce the core comparison.

Create a neutral benchmark CLI such as:

```bash
ghost-bench continuity
ghost-bench run benchmark.yaml
```

## Benchmark arms

Support:

```text
CMI persisted state
recent-window history
full history
LLM reducer
deterministic compact reducer
custom user implementation
```

A third party must be able to plug in a competing memory/state implementation.

## Benchmark outputs

Produce machine-readable and human-readable reports with state agreement,
host-behavior agreement, restart parity, context/token use, serialized bytes,
mutation latency, retrieval latency, persistence latency, model calls,
estimated/provider cost when available, and failure cases.

## Scientific rule

The benchmark is not:

> Watch the LLM fail while CMI wins.

It is:

> Reproduce the comparison yourself.

If a future model gets 100%, report it.

If a 30-line reducer beats CMI, report it.

If CMI loses, report it.

## Phase 4 exit criteria

A developer unfamiliar with the project can install the benchmark, configure a
supported model or custom implementation, execute one command, and reproduce a
documented continuity comparison.

# Phase 5 — Cross-Model Semantic Continuity

The goal is not identical generated dialogue.

The goal is to preserve authoritative continuity while the generative model
changes.

Require:

```text
same persistent CMI state
same deterministic host decision
same intended semantic behavior
acceptable surface realization
```

while varying model vendor, family, generation, size, and local/cloud
deployment.

A strong experiment should run a long-lived state through several model swaps
while CMI remains authoritative throughout.

## Phase 5 exit criteria

The model can be replaced without migrating authoritative behavioral state into
the new model's latent context and without changing CMI-owned host decisions.

# Phase 6 — Real Multi-Agent Production Workload

At this point, laboratory histories stop being the primary proof.

A real workload should exercise multiple persistent agents, relationships,
belief/evidence state, emotion, interpretation, attention, motives, continuity,
long histories, save/restore, schema upgrades, background persistence, model
replacement, and actual host decisions.

Ghost Revolution may become a reference consumer again, but it must not become
the definition of the benchmark.

## Strong comparison baseline

Do not compare only CMI vs no memory.

Compare against a competent purpose-built application state + ordinary
persistence/database + hand-written reducer implementation.

The benchmark should answer:

> For what workload does adopting CMI produce better continuity,
> maintainability, recovery, or integration properties than a competent custom
> implementation, and what does that advantage cost?

## Phase 6 exit criteria

CMI has a demonstrated workload where its guarantees justify its additional
abstraction and operational cost.

# Phase 7 — Integration Surface + Product Hardening

After the architecture survives the earlier phases, expose thin integrations.

Potential references:

```text
plain Python
service / FastAPI
Godot
Unreal
agent-framework adapter
```

Adapters remain thin.

CMI should not absorb rendering, animation, pathfinding, LLM-provider logic,
game mechanics, UI, or network orchestration.

## CLI direction

A `ghost-cmi` CLI should exist only if it earns a real operational role.

Useful commands may include:

```bash
ghost-cmi inspect save.cmi
ghost-cmi validate save.cmi
ghost-cmi migrate save.cmi --to 2.0
ghost-cmi diff before.cmi after.cmi
ghost-cmi recover journal.cmi
ghost-cmi benchmark benchmark.yaml
```

## API cleanup

Reduce duplicate/legacy public surface where compatibility permits.

New API surface must justify itself through a real integration need.

# Phase 8 — Operational / Enterprise Hardening

Only after the preceding layers work should CMI investigate concurrent
readers/writers, multi-process access, remote durability, replication,
observability, structured tracing, failure injection, corruption recovery,
large-state storage, bulk migration orchestration, resource quotas, and
security boundaries.

Not all of these belong inside CMI Core.

CMI should not accidentally become a database server, message broker, workflow
orchestrator, agent framework, and monitoring platform at the same time.

Integration is often preferable to ownership.

# Engineering Gates Across Every Phase

100% statement and branch coverage remain required but are not sufficient.

Every production change should also be evaluated for unnecessary complexity,
duplicate logic, dead/unreachable code, oversized functions/modules, excessive
API surface, architecture-boundary violations, determinism, mutation
resistance, restart parity, migration safety, performance regressions, memory
regressions, storage amplification, maintainability, failure recovery, and
rollback safety.

## Performance rule

No performance result becomes a requirement after seeing the measurement.

Thresholds and SLOs must be declared before the adjudication run.

Timing remains telemetry when no threshold was predeclared.

# Stop Conditions

A subsystem should be simplified or removed when a smaller replacement:

1. preserves required public behavior;
2. survives prospective/out-of-family testing;
3. preserves downstream host decisions that matter;
4. preserves persistence/restart guarantees;
5. does not worsen operational or maintenance cost.

A more complex mechanism should not be added unless a concrete failure
demonstrates missing representational capacity.

A research series should stop when its original question has been answered well
enough to make the next engineering decision.

Do not extend a closed experiment chain merely to accumulate more favorable
numbers.

# Architecture Direction

The target conceptual boundary is:

```text
                 GhoCentric CMI
                      │
              ┌───────┴────────┐
              │                │
           CMI Core        CMI Modules
              │                │
    deterministic graph     relationship
    transition engine       emotion
    persistence             epistemic
    recovery                interpretation
    migration               attention
    provenance              motives
    query / index           continuity
              │                │
              └───────┬────────┘
                      │
                 host schemas
                      │
             ┌────────┼─────────┐
             │        │         │
           games    agents    services
```

The psychology work is not discarded.

It becomes the first sophisticated reference schema built on a more general
continuity substrate.

# Execution Order

The current execution order is:

```text
1. State-minimization audit
2. Core / schema separation design
3. Invariant-validation + provenance-growth gates
4. Production persistence lifecycle
5. Schema evolution / deterministic migration
6. ghost-bench
7. Cross-model semantic continuity
8. Real multi-agent production workload
9. Integration / API / product hardening
10. Operational / enterprise hardening
```

The ordering is deliberate.

Do not optimize persistence before deciding what belongs in Core.

Do not build migration machinery before defining the long-term schema boundary.

Do not claim model portability before CMI can survive its own version changes.

Do not call CMI infrastructure-ready before it survives real host constraints.

# Claims Boundary

The roadmap does not target or imply proof of consciousness, sentience, AGI,
psychological realism, or universal superiority over every alternative
memory/state architecture.

The product claim remains narrower:

> **CMI is an opinionated deterministic state engine for software that needs
> structured state to persist, survive restart and evolution, and remain usable
> by a host over long-lived execution.**
