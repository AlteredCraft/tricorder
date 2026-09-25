# ADR-0012. The live model writes prose only; the host owns measurements

Status: Active · Decided: 2026-09-22 · Revised: 2026-09-24 (prose numbers checked; provider moved to config; raw-audio scope narrowed to the text model) · Evidence: [G-0002.01](../plans/G-0002.01-guided-ab-slice.md#observed) (`openrouter-smoke.json` · `71aebd5`, `3e6e655`)

## Decision

- The Mac verifies raw captures and computes every measurement and comparison. The text model gets only verified summaries plus fixture and operator context, never raw captures, network configuration or credentials.
- The model returns bounded prose and the exact ordered capture IDs through strict structured output. The host rejects anything else and builds every numeric, identity and deadline field itself.
- **Prose may not state a measurement the host didn't supply.** A number with a unit (dB, dBFS, Hz, kHz, counts) must match a host value of that unit, allowing rounding and ignoring sign, or the reply is rejected (`unbacked_numbers` in `tools/investigation.py`). Unitless numbers, such as distances in advice, are unchecked.
- No automatic retries. A provider failure or rejection fails the turn visibly, never falling back to the mock. The key stays in a Mac-local file.
- Provider and model are configuration (`--provider`, `--model`, `--env`); the current choice and timing are in the spec.
- Audio sent to a speech provider is decided separately.

**Alternatives:**
- Model-generated numbers: weakens provenance.
- Operator review as the only check: a person holding the device can't verify numbers.
- Host-templated number sentences: stricter but stilted; in reserve if unit checks prove leaky.
- A separate live protocol: duplicates validation.

## Consequences

- A reply that misstates a measurement is rejected and the turn becomes incomplete. The prompt asks for measured values only as given.
- Qualitative claims ("louder", "likely due to…") stay unchecked.
- Spoken output must use the checked text verbatim, which rules out speech-to-speech models.
