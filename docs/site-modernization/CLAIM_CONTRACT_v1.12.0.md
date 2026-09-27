# GhoCentric CMI website claim contract — DRAFT

This is the pre-build claim boundary for the modern website. Claims must remain no stronger than the evidence behind the v1.12.0 release.

## Primary product identity

Use:

> **GhoCentric CMI**
> Deterministic continuity and memory infrastructure for long-lived agents and reactive systems.

A concise secondary description may call it:

> An opinionated deterministic state engine.

Do not define the product primarily as consciousness, an autonomous mind, an LLM, or an NPC dialogue generator.

## Current public package facts

- Distribution: `ghocentric-ghost-engine`
- Current producer version: `1.12.0`
- Python import package: `ghost`
- Python requirement: `>=3.9`
- License: `Apache-2.0`
- Core runtime dependencies: `0`
- Optional OpenAI transport: `httpx>=0.27,<1`
- Existing CLI commands retained: `13`
- Snapshot schema: `1.0`

Safe install copy:

```bash
pip install ghocentric-ghost-engine
```

Optional OpenAI transport:

```bash
pip install "ghocentric-ghost-engine[openai]"
```

## Safe capability claims

The website may describe CMI as providing deterministic structured state transitions and persistent structured state such as relationships, observations/beliefs, attention, motives, interpretation, and continuity where those statements correspond to the maintained package.

It may state that JSON-safe snapshot/restore is supported and that the release gate verified exact snapshot/restore for the released package.

It may state that CMI does not require an LLM for its core state behavior.

It may state that the browser proof makes zero LLM calls **only if the modern browser proof actually continues to do so after the v1.12.0 port is tested**.

## Host-application boundary

The site should say clearly that CMI does not own graphics, animation, dialogue generation, or final application behavior merely because it stores state that can inform those systems.

The host application/game remains responsible for how CMI state is converted into actions, presentation, dialogue, and other effects.

## Persistence precision

Current Stage-10 persistence must be described as the current private, explicit opt-in shadow candidate with the full snapshot remaining authoritative.

Do **not** present the Stage-9 two-slot atomic recovery/migration research protocol as current Stage-10 production behavior.

Do not turn research telemetry into a production latency promise or SLO.

## Browser-demo precision

The existing preserved site currently runs:

- Pyodide: `0.28.3`
- PyPI package pin: `1.10.0`

The modern site must not claim the browser runs v1.12.0 until a clean browser/Pyodide compatibility experiment demonstrates that exact package and the demos pass their deterministic expected-output checks.

## Evidence presentation

Detailed test/coverage counts belong in an Evidence / Engineering section, not in the opening product definition.

Coverage demonstrates exercised implementation paths under the maintained tests; it is not, by itself, proof of universal correctness or production suitability.

## Link authority

Maintained product/source links should target:

- Repository: https://github.com/GhoCentric/GhoCentric-CMI
- v1.12.0 release: https://github.com/GhoCentric/GhoCentric-CMI/releases/tag/v1.12.0
- PyPI v1.12.0: https://pypi.org/project/ghocentric-ghost-engine/1.12.0/

The `/ghost-prototype/` site remains legacy history until the new CMI Pages deployment passes its public verification gate.
