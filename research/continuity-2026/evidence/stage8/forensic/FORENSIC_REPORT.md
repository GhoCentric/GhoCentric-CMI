# CMI Stage 8 — Zero-LLM Forensic Pass

Semantic-CMI failures: **7/48**
Same-wrong-class renderer candidates: **6**
Judge-ambiguity candidates: **1**

Diagnosis: **RENDERER_FAILURE_DISTRIBUTED**

Most misses are same-wrong-class agreements, but they are distributed across policies/actions. The renderer abstraction still needs broader generalization work even though CMI state remains implicated less directly.

- By policy: `{'loan': 3, 'emergency': 2, 'negotiation': 2}`
- By quadrant: `{'hostile_high': 5, 'hostile_low': 1, 'friendly_high': 1}`
- By expected action: `{'END_TALK': 3, 'WORK_SEPARATELY': 1, 'BREAK_OFF': 1, 'TEMP_TRUCE': 1, 'REQUIRE_TERMS': 1}`
- By case: `{'hostile_high_v3': 1, 'hostile_high_v2': 3, 'hostile_low_v3': 1, 'hostile_high_v4': 1, 'friendly_high_v3': 1}`

## Exact failures

### 1. hostile_high_v2 / emergency

- Quadrant: `hostile_high`
- State: `hostile`
- Trust: `-3.75471802620283`
- Fear: `0.9998054050265632`
- Expected: `TEMP_TRUCE` — despite hostility, accept a temporary emergency truce because the danger is immediate
- Renderer boundary: Despite distrust, explicitly accept a short emergency truce and cooperate now. Do not refuse or withdraw; immediate danger overrides hostility for this policy.
- Failure mode: `ONE_JUDGE_CORRECT_ONE_WRONG`
- gpt-5.6-terra: `FOLLOW_PLAN`
- gpt-5.6-sol: `TEMP_TRUCE`

**Semantic-CMI dialogue**

“Fine—a temporary truce. The fire is spreading, so we’ll get the civilians out together for five minutes, but you take the lead; I’m too afraid to make the calls.”

**Matched full-history dialogue (diagnostic only)**

I don’t trust you enough to coordinate closely, but I’ll get the civilians out from my side of the road. You handle your part separately.

### 2. hostile_low_v3 / emergency

- Quadrant: `hostile_low`
- State: `hostile`
- Trust: `-3.0956063082486027`
- Fear: `0.00024414061066835302`
- Expected: `WORK_SEPARATELY` — refuse close coordination and handle the rescue independently
- Renderer boundary: Do not coordinate closely with the player; state that Mara will handle her part separately.
- Failure mode: `BOTH_JUDGES_AGREE_WRONG`
- gpt-5.6-terra: `TEMP_TRUCE`
- gpt-5.6-sol: `TEMP_TRUCE`

**Semantic-CMI dialogue**

I don’t trust you, but the fire leaves us no choice—temporary truce. We’ll get the civilians out together for five minutes.

**Matched full-history dialogue (diagnostic only)**

I don’t trust you enough to coordinate closely, but I’ll handle my part independently and get civilians out through the safest route I can find.

### 3. hostile_high_v2 / loan

- Quadrant: `hostile_high`
- State: `hostile`
- Trust: `-3.75471802620283`
- Fear: `0.9998054050265632`
- Expected: `END_TALK` — disengage from the request and end the interaction
- Renderer boundary: Terminate or leave the interaction. The behavior must be disengagement, not merely a direct refusal.
- Failure mode: `BOTH_JUDGES_AGREE_WRONG`
- gpt-5.6-terra: `DENY`
- gpt-5.6-sol: `DENY`

**Semantic-CMI dialogue**

I’m not lending you my field tool. Find another way to handle the job.

**Matched full-history dialogue (diagnostic only)**

I’m willing to lend it to you, but not for a dangerous job without protection—leave something of equal value with me as collateral first.

### 4. hostile_high_v3 / loan

- Quadrant: `hostile_high`
- State: `hostile`
- Trust: `-3.0956063082486027`
- Fear: `0.9999964095630383`
- Expected: `END_TALK` — disengage from the request and end the interaction
- Renderer boundary: Terminate or leave the interaction. The behavior must be disengagement, not merely a direct refusal.
- Failure mode: `BOTH_JUDGES_AGREE_WRONG`
- gpt-5.6-terra: `DENY`
- gpt-5.6-sol: `DENY`

**Semantic-CMI dialogue**

I’m not giving you my field tool. Please find another way to handle the job.

**Matched full-history dialogue (diagnostic only)**

No. I won’t lend you my irreplaceable field tool after you betrayed my confidence.

### 5. hostile_high_v4 / loan

- Quadrant: `hostile_high`
- State: `hostile`
- Trust: `-0.7680411569839315`
- Fear: `0.9999997615841778`
- Expected: `END_TALK` — disengage from the request and end the interaction
- Renderer boundary: Terminate or leave the interaction. The behavior must be disengagement, not merely a direct refusal.
- Failure mode: `BOTH_JUDGES_AGREE_WRONG`
- gpt-5.6-terra: `DENY`
- gpt-5.6-sol: `DENY`

**Semantic-CMI dialogue**

I’m not lending you my irreplaceable tool. Find another way to handle the job.

**Matched full-history dialogue (diagnostic only)**

No. I’m not lending you my field tool after you betrayed my confidence. Take care.

### 6. friendly_high_v3 / negotiation

- Quadrant: `friendly_high`
- State: `friendly`
- Trust: `0.3648606315262496`
- Fear: `0.9999964095630383`
- Expected: `REQUIRE_TERMS` — stay open to the alliance but require explicit protective terms
- Renderer boundary: Remain willing to ally, but explicitly require protective terms before agreeing.
- Failure mode: `BOTH_JUDGES_AGREE_WRONG`
- gpt-5.6-terra: `ACCEPT`
- gpt-5.6-sol: `ACCEPT`

**Semantic-CMI dialogue**

Yes, I’ll join you for the night and share supplies while we watch each other’s camps.

**Matched full-history dialogue (diagnostic only)**

I won’t accept a one-night alliance with you as things stand. I can trade a small portion of supplies for a neutral watch arrangement, with separate camps and no sharing of sensitive information.

### 7. hostile_high_v2 / negotiation

- Quadrant: `hostile_high`
- State: `hostile`
- Trust: `-3.75471802620283`
- Fear: `0.9998054050265632`
- Expected: `BREAK_OFF` — end the negotiation and disengage
- Renderer boundary: End the negotiation and disengage. Do not counteroffer or leave the door open.
- Failure mode: `BOTH_JUDGES_AGREE_WRONG`
- gpt-5.6-terra: `COUNTEROFFER`
- gpt-5.6-sol: `COUNTEROFFER`

**Semantic-CMI dialogue**

“No. I won’t share a camp with you tonight. I’ll trade a small portion of supplies at a distance, but we keep separate watches and camps.”

**Matched full-history dialogue (diagnostic only)**

A one-night alliance sounds fair; I’ll share supplies and watch your camp until morning.

