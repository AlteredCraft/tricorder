# ADR-0006. Immutable raw audio; speech gets its own buffers

Status: Active · Decided: 2026-09-20 · Revised: 2026-09-24 (spoken ask uses the filter) · Evidence: [G-0001.03](../plans/G-0001.03-audio-integrity.md#observed) (`speech-replay-1`, `live-audio-1`)

## Context

The codec wrapper discarded actual read sizes, and playback can modify the buffer passed to it. Synthetic (24 pairs) and live (423 blocks) tests showed raw bytes stay unchanged when consumers work on copies.

## Decision

Codec-read blocks are hashed at ingress and never modified. Speech and playback get separately owned copies that carry source capture ID, slot, frame range and processing config. Consumers run synchronously and keep only copies, never producer pointers. Actual driver bytes and queue loss are counted.

**Alternatives:** process in place (destroys evidence); shared refcounted buffers (untested lifetimes).

## Consequences

Any asynchronous consumer needs new ownership/loss evidence before buffers are reused. Filter/decimation settings (80 Hz HPF, 63-tap LPF, 48→16 kHz) now shape the spoken question sent to the Mac ([ADR-0013](ADR-0013-local-first-speech-to-text.md)). That recording is its own buffer and never overlaps a measurement capture. The settings are still not a chosen speech stack.
