# CMI architecture boundary

GhoCentric CMI is the deterministic state and continuity layer.

The maintained boundary is intentionally narrower than earlier research
language:

- the host supplies events, observations, facts, and integration inputs;
- CMI maintains structured deterministic state;
- snapshots and persistence carry authoritative application state;
- language models may consume or propose information around that state, but
  generated output is not automatically promoted to authoritative state;
- private persistence experiments remain opt-in until their production cost and
  operational boundaries justify broader exposure.

The public API remains the existing `ghost` package surface during the v1.12
repository extraction.
