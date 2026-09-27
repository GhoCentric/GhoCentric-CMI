# Phase 4E clarity contract

The homepage now separates three questions:

1. What state does CMI model? — section 01.
2. Where does CMI sit and what does using it look like? — section 02.
3. Where does CMI's responsibility stop? — section 03.

The architecture trace no longer repeats the complete state-layer inventory.

The homepage exposes only the core install command. Optional OpenAI transport remains
a package capability, but its install command is intentionally omitted from the homepage
to avoid implying that CMI requires OpenAI or an LLM.

The minimal API lifecycle shown on the homepage is executed against current v1.12.0
source by the Phase-4E build gate before the example is accepted.
