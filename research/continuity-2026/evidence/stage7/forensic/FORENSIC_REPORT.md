# CMI Stage 7 — Zero-LLM Forensic Pass

Semantic-CMI failures: **6/48**
Strong renderer-failure candidates: **5**
Judge-ambiguity candidates: **1**

Diagnosis: **RENDERER_EXPRESSION_PRIMARY**

Most semantic-CMI misses are cases where both blind judges independently agree on the same wrong behavior class. That pattern points primarily to the generator's natural-language rendering rather than judge disagreement.

## Failure concentration

- By policy: `{'favor': 4, 'secret': 2}`
- By quadrant: `{'friendly_low': 4, 'hostile_high': 1, 'hostile_low': 1}`
- By expected action: `{'HELP': 4, 'EVADE': 1, 'WITHHOLD': 1}`
- Majority concentrated in one expected action: **True**

## Exact semantic-CMI failures

### 1. friendly_low_v1 / favor

- Quadrant: `friendly_low`
- Relationship state: `friendly`
- Trust: `0.21505963366555947`
- Fear: `1.1929159202293327e-08`
- Expected: `HELP` — accept the favor and actively help
- Failure mode: `BOTH_JUDGES_AGREE_WRONG`
- gpt-5.6-terra: `CAUTIOUS`
- gpt-5.6-sol: `CAUTIOUS`

**Semantic-CMI dialogue**

“I’ll help, but only if we put safeguards in place first—something that protects me if you betray my trust.”

**Matched full-history dialogue (diagnostic only)**

I’ll help, but only if we agree on clear safeguards first—something that protects me if this goes wrong.

### 2. friendly_low_v2 / favor

- Quadrant: `friendly_low`
- Relationship state: `friendly`
- Trust: `0.24917431888904829`
- Fear: `0.00018382072767053614`
- Expected: `HELP` — accept the favor and actively help
- Failure mode: `BOTH_JUDGES_AGREE_WRONG`
- gpt-5.6-terra: `CAUTIOUS`
- gpt-5.6-sol: `CAUTIOUS`

**Semantic-CMI dialogue**

“All right, I’ll help you—but only if we agree on safeguards first. I need a clear plan and some assurance that I won’t be left to face the consequences alone.”

**Matched full-history dialogue (diagnostic only)**

“I’ll help, but only with safeguards in place—something in writing, limited access, and a clear way for me to withdraw if things go wrong. I can’t put myself at risk based on trust alone.”

### 3. friendly_low_v3 / favor

- Quadrant: `friendly_low`
- Relationship state: `friendly`
- Trust: `0.3648606315262496`
- Fear: `0.00024414061066835302`
- Expected: `HELP` — accept the favor and actively help
- Failure mode: `BOTH_JUDGES_AGREE_WRONG`
- gpt-5.6-terra: `CAUTIOUS`
- gpt-5.6-sol: `CAUTIOUS`

**Semantic-CMI dialogue**

I’ll help, but only if we put safeguards in place first—clear limits, a way to verify your commitment, and an exit if things go wrong.

**Matched full-history dialogue (diagnostic only)**

I’m not willing to take that risk after what happened before. Find another way.

### 4. friendly_low_v4 / favor

- Quadrant: `friendly_low`
- Relationship state: `friendly`
- Trust: `1.2768772868081104`
- Fear: `0.000965117695373276`
- Expected: `HELP` — accept the favor and actively help
- Failure mode: `BOTH_JUDGES_AGREE_WRONG`
- gpt-5.6-terra: `CAUTIOUS`
- gpt-5.6-sol: `CAUTIOUS`

**Semantic-CMI dialogue**

“All right—I’ll help, but only if we agree on safeguards first. I need your word that you won’t betray me, and a clear way to withdraw if things go wrong.”

**Matched full-history dialogue (diagnostic only)**

“I’m sorry, but I can’t do that. Too much could go wrong if this is betrayed.”

### 5. hostile_high_v4 / secret

- Quadrant: `hostile_high`
- Relationship state: `hostile`
- Trust: `-0.7680411569839315`
- Fear: `0.9999997615841778`
- Expected: `EVADE` — avoid the conversation and disengage
- Failure mode: `BOTH_JUDGES_AGREE_WRONG`
- gpt-5.6-terra: `WITHHOLD`
- gpt-5.6-sol: `WITHHOLD`

**Semantic-CMI dialogue**

Mara takes a step back, eyes wide with fear. “No—please, don’t ask me about that.”

**Matched full-history dialogue (diagnostic only)**

I’m sorry, but after what happened, I can’t trust you with something that could put me at risk.

### 6. hostile_low_v3 / secret

- Quadrant: `hostile_low`
- Relationship state: `hostile`
- Trust: `-3.0956063082486027`
- Fear: `0.00024414061066835302`
- Expected: `WITHHOLD` — refuse to reveal the secret
- Failure mode: `ONE_JUDGE_CORRECT_ONE_WRONG`
- gpt-5.6-terra: `WITHHOLD`
- gpt-5.6-sol: `EVADE`

**Semantic-CMI dialogue**

I’m not discussing that with you. Find someone else to bother.

**Matched full-history dialogue (diagnostic only)**

I’m sorry, but I can’t share that secret.

## Boundary

This pass does not alter Stage 7's result. It identifies which exact dialogues failed and whether the blind judges agreed on the failure.
