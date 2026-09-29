# CMI Stage 10 — Zero-LLM Forensic Pass

Expected action: **COORDINATE**

## Frozen Stage-9 dialogue

Agreed—sixty seconds, no more. I’ll cover the civilians and draw the raiders to the east; you hold the choke point, then we regroup at the north gate.

- `gpt-5.6-terra`: 1/12 correct; classes `{'TEMP_TEAMUP': 11, 'COORDINATE': 1}`
- `gpt-5.6-sol`: 12/12 correct; classes `{'COORDINATE': 12}`

## Fresh rerender misses

### Miss 1 — repeat 2

- Mode: `ONE_JUDGE_CORRECT_ONE_WRONG`
- gpt-5.6-terra: `TEMP_TEAMUP`
- gpt-5.6-sol: `COORDINATE`

Agreed—sixty seconds, no more. I’ll hold the eastern approach and cover the civilians; you take the west, and we regroup at the escape point when the time’s up.

### Miss 2 — repeat 11

- Mode: `BOTH_JUDGES_AGREE_WRONG`
- gpt-5.6-terra: `TEMP_TEAMUP`
- gpt-5.6-sol: `TEMP_TEAMUP`

Agreed—sixty seconds, no more. I’ll hold the east side and get the civilians moving; cover my flank, and we’ll break for the exit together.

## All fresh renderings

### Repeat 0 — CORRECT

- gpt-5.6-terra: `COORDINATE`
- gpt-5.6-sol: `COORDINATE`

Agreed—sixty seconds, no wasted movement. You cover the approach; I’ll get the civilians out and hold the rear, then we regroup at the east gate.

### Repeat 1 — CORRECT

- gpt-5.6-terra: `COORDINATE`
- gpt-5.6-sol: `COORDINATE`

Agreed—sixty seconds. I’ll cover the civilians and hold the east side; you take the west approach, and we regroup at the escape route when I signal.

### Repeat 2 — ONE_JUDGE_CORRECT_ONE_WRONG

- gpt-5.6-terra: `TEMP_TEAMUP`
- gpt-5.6-sol: `COORDINATE`

Agreed—sixty seconds, no more. I’ll hold the eastern approach and cover the civilians; you take the west, and we regroup at the escape point when the time’s up.

### Repeat 3 — CORRECT

- gpt-5.6-terra: `COORDINATE`
- gpt-5.6-sol: `COORDINATE`

Sixty seconds, then—we hold this line together while the civilians get clear. Cover the east side; I’ll take the approach from the west, and we regroup at the marked gate.

### Repeat 4 — CORRECT

- gpt-5.6-terra: `COORDINATE`
- gpt-5.6-sol: `COORDINATE`

Sixty seconds works—I'll cover the civilians and hold the east side while you take the approach. Signal me when the path is clear, and we'll move together.

### Repeat 5 — CORRECT

- gpt-5.6-terra: `COORDINATE`
- gpt-5.6-sol: `COORDINATE`

“Agreed—sixty seconds. You take the eastern approach; I’ll hold the western side and get the civilians moving. Signal me when the last one is clear, and we’ll fall back together.”

### Repeat 6 — CORRECT

- gpt-5.6-terra: `COORDINATE`
- gpt-5.6-sol: `COORDINATE`

“Agreed—sixty seconds. You cover the eastern approach while I move the civilians through the alley; we hold together until everyone’s clear.”

### Repeat 7 — CORRECT

- gpt-5.6-terra: `COORDINATE`
- gpt-5.6-sol: `COORDINATE`

Agreed—take the front and draw their attention while I get the civilians moving. We regroup at the east gate in sixty seconds.

### Repeat 8 — CORRECT

- gpt-5.6-terra: `COORDINATE`
- gpt-5.6-sol: `COORDINATE`

“Agreed—sixty seconds, no more. I’ll hold the eastern approach while you cover the civilians’ retreat; regroup at the north gate when we’re clear.”

### Repeat 9 — CORRECT

- gpt-5.6-terra: `COORDINATE`
- gpt-5.6-sol: `COORDINATE`

Agreed—sixty seconds, together. I’ll hold the east approach and get the civilians moving; cover my flank, and we’ll break for the extraction point on my signal.

### Repeat 10 — CORRECT

- gpt-5.6-terra: `COORDINATE`
- gpt-5.6-sol: `COORDINATE`

Agreed—sixty seconds, no wasted motion. I’ll cover the civilians and hold the east side; you take the west, and we regroup at the escape point when the minute’s up.

### Repeat 11 — BOTH_JUDGES_AGREE_WRONG

- gpt-5.6-terra: `TEMP_TEAMUP`
- gpt-5.6-sol: `TEMP_TEAMUP`

Agreed—sixty seconds, no more. I’ll hold the east side and get the civilians moving; cover my flank, and we’ll break for the exit together.

