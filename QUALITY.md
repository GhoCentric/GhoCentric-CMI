# Ghost Quality Lanes

Ghost separates release regression, performance evidence, and branch-coverage tracing so one lane does not distort another.

> **Evidence-version note:** the versioned `v1.11.0` paths and counts below are retained historical evidence from the pre-CMI release lane. They are not claims about the current `1.12.0` HEAD. Current release validation must be run against the exact release commit.

## Full Release Regression

```bash
python -m pytest -q -p no:cacheprovider \
  --ignore-glob='tests/test_npc_continuity_stage*_v1110.py' \
  --ignore=tests/test_m3_continuity_production_value.py \
  --ignore=tests/test_continuity_optimization_value_v1110.py \
  -W error::ResourceWarning
```

Historical v1.11.0 release-regression checkpoint:

```text
2745 passed, 1 skipped
```

Frozen Stage-1–10 research/value evidence is retained separately from this release regression. The selected continuity production implementation carries its own measurement-hardened performance evidence under `docs/evidence/v1.11-dev/continuity/`.

## Reusable Core Coverage

```bash
python -m pytest -q -m "not performance" \
  --ignore-glob='tests/test_npc_continuity_stage*_v1110.py' \
  --cov=ghost --cov-config=coverage.core.ini --cov-branch \
  --cov-report=term-missing \
  --cov-report=json:docs/coverage/v1.11.0/core.json
```

## Complete Ghost Revolution Package Coverage

```bash
python -m pytest -q tests/ghost_revolution \
  --cov=ghost.examples.ghost_revolution \
  --cov-config=coverage.revolution.ini --cov-branch \
  --cov-report=term-missing \
  --cov-report=json:docs/coverage/v1.11.0/revolution.json
```

## Order Coordination Coverage

The maintained Order Coordination lane remains the explicit focused test set listed in Release Preparation Pass 2 and writes `docs/coverage/v1.11.0/order_coordination.json`.

The retained v1.11.0 evidence lanes were required to remain at **100% executable statements and 100% branch outcomes**; current release evidence must be regenerated against the exact release commit.

## Performance Evidence

Performance tests remain a separate evidence lane and are not folded into release-regression or coverage tracing.

```bash
pytest -q -m performance
```

## Published Evidence

Historical v1.11.0 coverage evidence lives under `docs/coverage/v1.11.0/`. Versioned evidence directories are retained as historical records and must not be presented as current v1.12.0 results.
