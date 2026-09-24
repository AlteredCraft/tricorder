# ADR-0012. The live model writes prose only; the host owns measurements

Status: Active · Decided: 2026-09-22 · Revised: 2026-09-24 (prose numbers checked; provider choice moved to config; raw-audio scope narrowed to the text model) · Evidence: [G-0002.01](../plans/G-0002.01-guided-ab-slice.md#observed) (`openrouter-smoke.json`)

## Decision

- The Mac verifies raw captures and computes every measurement and comparison. The text model receives only verified summaries plus fixture and operator context. It never receives raw captures, network configuration or credentials.
- The model returns bounded prose and the exact ordered capture IDs, through strict structured output. The host rejects anything else, and it builds every numeric, identity and deadline field itself.
- **Prose may not state a measurement the host didn't supply.** A number with a measurement unit (dB, dBFS, Hz, kHz, counts) must match a host value of the same unit. Rounding to the stated precision is allowed and sign is ignored. Otherwise the reply is rejected (`unbacked_numbers` in `tools/investigation.py`). Numbers without a unit, such as distances in advice, are not checked.
- There are no automatic retries. A provider failure or rejection makes the turn fail visibly and never falls back to the mock. The key stays in a Mac-local file.
- Provider and model are configuration (`--provider`, `--model`, `--env`), not part of this decision. The current choice and its timing are recorded in the spec.
- Audio sent to a speech provider is outside this ADR and is decided separately.

**Alternatives:**
- Model-generated numbers: weakens provenance.
- Operator review as the only check on prose: a person holding the device can't verify the numbers.
- Host-templated number sentences: stricter, but less natural prose. Keep it in reserve if unit checks prove leaky.
- A separate live protocol: duplicates validation.

## Consequences

- A reply that misstates a measurement is rejected, and that turn becomes incomplete. The prompt asks the model to state measured values only as given.
- Qualitative claims in prose ("louder", "likely due to…") are still unchecked.
- Spoken output must use the checked text verbatim. Speech-to-speech models that generate their own speech can't meet this.
