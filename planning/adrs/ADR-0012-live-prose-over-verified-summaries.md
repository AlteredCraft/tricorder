# ADR-0012. The live model writes prose only; the host owns measurements

Status: Active · Decided: 2026-09-22 · Evidence: [G-0002.01](../plans/G-0002.01-guided-ab-slice.md#observed) (`openrouter-smoke.json`)

## Decision

The Mac verifies raw captures and computes all measurements and comparisons. The model receives verified summaries plus fixture/operator context. It returns bounded prose and the exact ordered capture IDs, and the host rejects anything else and builds all numeric/identity/deadline fields itself. Provider: OpenRouter `openai/gpt-5.6-sol` via the async OpenAI-compatible Responses API, with strict structured output, no stored state and no automatic retries. Provider failure never falls back to mock. The key stays in a Mac-local file. Raw audio and Wi-Fi credentials are never sent.

**Alternatives:** model-generated numbers (weakens provenance); a separate live protocol (duplicates validation).

## Consequences

Prose can still be wrong, so operator review is required. Speech provider/codec is not yet chosen.
