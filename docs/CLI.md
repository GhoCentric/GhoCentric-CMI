# CLI compatibility

The repository extraction preserves the existing 13 console commands so the
move to GhoCentric-CMI does not break established workflows.

## CMI-relevant reference commands

- `ghost-epistemic-demo`
- `ghost-order-coordination-demo`
- `ghost-npc-demo`
- `ghost-diagnostics-demo`

## Additional reference commands

- `ghost-demo`
- `ghost-social-demo`
- `ghost-temperament-demo`
- `ghost-threat-response-demo`

## Legacy/reference compatibility commands

- `ghost-shopkeeper-demo`
- `ghost-math-demo`
- `ghost-revolution-demo`
- `ghost-revolution-dev`
- `ghost-revolution-llm-dev`

The last group remains functional for v1.12 compatibility but is not presented
as the primary CMI infrastructure interface.

A future `ghost-cmi` command may consolidate infrastructure-facing operations,
but this extraction does not introduce it.
