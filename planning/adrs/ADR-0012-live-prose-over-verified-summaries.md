# ADR-0012. Keep live-model prose outside the measurement authority

Status: Active
Decided: 2026-09-22
Evidence: [G-0002.01 observations](../plans/G-0002.01-guided-ab-slice.md#observed), approved OpenRouter summary probes
Replaces: None

## Context

The user selected OpenRouter `openai/gpt-5.6-sol`, supplied a local credential file,
and explicitly approved sending two stored A/B evidence summaries. Actual guide
and compare calls return in 3.21 and 2.93 seconds. They preserve reference joins
and correctly describe the contrary +0.94 dB digital RMS result. This is live
text-model evidence over stored recordings, not handheld speech or usefulness
acceptance.

## Options considered

1. Let the model generate structured measurement values: weakens provenance.
2. Build a separate live protocol: duplicates device/host state and validation.
3. Replace only the prose provider behind the existing verified evidence contract.

## Decision

Use option 3. The Mac verifies raw captures and computes measurements/comparisons.
The model receives verified summaries and fixture/operator context, then returns
bounded prose and the exact ordered capture IDs. The host rejects malformed,
incomplete and wrong-reference responses and constructs all numeric/identity/
deadline fields itself. The device retains its independent validation and local
capture controls. There is no silent fallback to mock results.

Use the asynchronous OpenAI-compatible Responses API through the explicitly
selected OpenRouter endpoint/model. Request strict structured output and supported
parameters, disable stored conversation state and automatic retries, and retain
the existing device deadline. Keep the API key on the Mac in a provider-specific
environment or literal local configuration file. Do not forward it to the device.
Raw recordings and network credentials are absent from text-model prompts.

## Consequences and limits

Prose can still contain semantic errors even when structured joins pass; transcript
review and operator understanding/usefulness remain required. Retain provider,
model and monotonic host inference timing. SDK errors are replaced by fixed
failure reasons rather than logging arbitrary remote error bodies.

This extends ADR-0010's provider seam. It does not adopt a speech codec/model,
calibrate acoustics, prove latency distributions, or complete G-0002/G-0001.
Revisit the model, routing or deadline only through a recorded experiment.
