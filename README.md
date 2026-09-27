# GhoCentric CMI

**Continuity & Memory Infrastructure**

GhoCentric CMI is deterministic state, continuity, and persistence
infrastructure for long-lived agents and reactive systems.

It exists for applications where state accumulates over time: relationships,
observations, beliefs, attention, motives, history, and other structured state
must survive mutation, serialization, restart, recovery, and continued
execution without making a language model or other non-deterministic component
the authoritative source of truth.

## Current status

This working tree is a clean extraction from the validated Ghost v1.12-dev
Stage-10C state.

- Extraction source commit: `e76f93833d76d2bf759ffd191498762d0458b02d`
- PyPI distribution name: `ghocentric-ghost-engine`
- Python package/import: `ghost`
- Current package producer version: `1.12.0`
- Runtime dependencies: **0**
- Public API compatibility: preserved during extraction
- Existing CLI compatibility: **13/13 commands preserved**

The package version has intentionally **not** been renamed or bumped as part of
the repository move. Repository/product cleanup and compatibility-breaking
package migration are separate decisions.

## What CMI currently provides

- deterministic structured state transitions;
- JSON-safe snapshot and restore;
- relationship, epistemic, attention, motive, interpretation, and continuity
  state;
- lossless compact persistence for the validated persistence candidate;
- restart-and-continue parity under the tested scenarios;
- guarded corruption/version fallback;
- local single-host writer exclusion for the private shadow-persistence path;
- private, explicit opt-in shadow persistence where the full baseline remains
  authoritative.

Separate Stage-9 research prototypes established two-slot atomic recovery and
migration behavior under the tested fault-injection scenarios. Those
authoritative checkpoint/migration protocols are retained as research evidence
and are **not ported into the current Stage-10C production candidate**.

CMI is infrastructure. It is not an LLM, does not require an LLM, and does not
treat generated text as authoritative application state.

## Evidence boundary

The final Stage-10C adjudication reported:

- **7,706 production statements**
- **3,190 production branches**
- **100% maintained statement and branch coverage**
- **3,640 passed / 1 skipped** in the full non-research regression lane
- repeated real `GhostAPI` snapshot/mutation parity;
- verified restore and deterministic continuation parity;
- contention, corruption/version fallback, and rollback;
- actual process-exit recovery after baseline, candidate, and manifest atomic
  commit boundaries at each tested scale.

Those results establish the tested behavior of this implementation. They are
not a claim that CMI has already been validated across every game engine,
studio workload, distributed filesystem, or production deployment.

### Known performance boundary

The current shadow persistence path is synchronous and remains **explicit
opt-in**. In the Stage-10C Android/Termux telemetry, the 4,096-event case
measured about **39.8 ms** for the control snapshot and **1.47 s** for the
verified integrated shadow path (~36.95×). That is a measured limitation, not
a hidden benchmark win and not a latency SLO.

## Installation compatibility

The currently published package name remains:

```bash
pip install ghocentric-ghost-engine
```

Python imports remain:

```python
from ghost import GhostAPI

ghost = GhostAPI()
snapshot = ghost.snapshot()
restored = GhostAPI.from_snapshot(snapshot)

assert restored.snapshot() == snapshot
```

## Existing command compatibility

All reviewed commands remain declared in v1.12 extraction:

```text
ghost-demo
ghost-npc-demo
ghost-shopkeeper-demo
ghost-math-demo
ghost-diagnostics-demo
ghost-social-demo
ghost-temperament-demo
ghost-threat-response-demo
ghost-epistemic-demo
ghost-revolution-demo
ghost-revolution-dev
ghost-revolution-llm-dev
ghost-order-coordination-demo
```

These commands are compatibility/reference entry points. They are **not** all
the primary product interface.

The future CMI-facing CLI is planned around a single `ghost-cmi` command with a
small infrastructure-oriented subcommand surface. It is intentionally not
introduced by this extraction so the repository move does not silently change
runtime behavior.

## Reference applications

Ghost Revolution remains in the package for compatibility and as a reference
application. It should be understood as a consumer/demonstration of the engine,
not the definition of CMI itself.

## Repository history

The earlier `ghost-prototype` repository is the historical research and
development record. Active maintained-package work now lives in
**GhoCentric-CMI**. The old repository should remain available rather than
being rewritten to make the project appear cleaner in hindsight.

See `docs/legacy/README.md` and `EXTRACTION_PROVENANCE.md`.

## License

GhoCentric CMI is licensed under the Apache License, Version 2.0 (`Apache-2.0`).
See [`LICENSE`](LICENSE) for the full license terms.
