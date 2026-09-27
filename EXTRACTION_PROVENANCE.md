# Extraction provenance

This tree was extracted from:

- source repository: `GhoCentric/ghost-prototype`
- source branch: `v1.12-dev`
- source commit: `e76f93833d76d2bf759ffd191498762d0458b02d`
- target repository name: `GhoCentric-CMI`

Production Python source under `ghost/` is byte-for-byte identical to the
Stage-10C source commit. Only product-facing repository metadata/documentation
is rewritten during extraction.

Compatibility deliberately preserved:

- distribution: `ghocentric-ghost-engine`
- import package: `ghost`
- public API source
- 13 reviewed console entry points
- runtime dependency count: zero

The new repository is not initialized or pushed by the extraction script.
