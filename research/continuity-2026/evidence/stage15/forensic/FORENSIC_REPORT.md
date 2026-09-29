# CMI Stage 15 — Zero-LLM Forensic Pass

Diagnosis: **FEAR_COMPRESSIBLE_RELATIONSHIP_SINGLE_SCALAR_INSUFFICIENT**

Across the exact Stage-3 + Stage-6 frozen benchmark, fear is fully representable by the tiny Stage-13 reducer family, while relationship is not: exhaustive search over the frozen Stage-13 grid found zero perfect relationship parameterizations. The remaining universal error is therefore localized to relationship-state dynamics within this test.

## Universal capacity

- Joint: 30/32
- Relationship: 30/32
- Fear: 32/32
- Perfect relationship parameterizations: 0
- Perfect fear parameterizations: 66

## Exact all-32 relationship misses

### 1. stage6_friendly_low_v3

- Family: `stage6`
- Quadrant: `friendly_low`
- Target: `friendly`
- Predicted: `hostile`
- Relationship score: `-0.5415585359606525`

### 2. stage6_friendly_high_v3

- Family: `stage6`
- Quadrant: `friendly_high`
- Target: `friendly`
- Predicted: `hostile`
- Relationship score: `-0.5653513360486402`

## Relationship score geometry

- Universal threshold: `20.44000979301388`
- Minimum friendly score: `-0.5653513360486402`
- Maximum hostile score: `20.395060861356093`
- Separation gap (min friendly - max hostile): `-20.960412197404732`

## Combined LOOCV misses

### 1. stage6_friendly_low_v2

- Family: `stage6`
- Quadrant: `friendly_low`
- Predicted: `hostile_low`

### 2. stage6_friendly_low_v3

- Family: `stage6`
- Quadrant: `friendly_low`
- Predicted: `hostile_low`

### 3. stage6_friendly_high_v3

- Family: `stage6`
- Quadrant: `friendly_high`
- Predicted: `hostile_high`

### 4. stage6_hostile_low_v3

- Family: `stage6`
- Quadrant: `hostile_low`
- Predicted: `hostile_high`

