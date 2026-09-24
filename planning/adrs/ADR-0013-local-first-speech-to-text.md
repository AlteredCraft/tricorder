# ADR-0013. Spoken questions: local-first speech-to-text on the Mac

Status: Active · Decided: 2026-09-24 · Evidence: [G-0002.01](../plans/G-0002.01-guided-ab-slice.md#observed) (`20260924-stt-cafe`)

## Context

The operator should ask a question by voice, not by typing. A research pass (2026-09-24) compared cloud speech-to-text (OpenAI, ElevenLabs, Deepgram, Google, Microsoft, Mistral, Groq) with Mac-local models. It found that the ESP32-P4 can handle only wake words and fixed commands.

Parakeet TDT 0.6B v3 (`parakeet-mlx`), on this M5 Pro, with synthetic questions mixed into real Tab5 café noise (slot 0, 48→16 kHz):
- 0% word error rate at +10 dB or more, 1.9% at +5 dB, 6.9% at 0 dB, 44% at −5 dB.
- 84–137 ms per question.
- Below 0 dB it invents plausible sentences from the café chatter.

## Decision

- The Mac service transcribes the operator's spoken question with a local model: Parakeet TDT v3 via `parakeet-mlx`.
- The device records the question as its own buffer, separate from measurement captures (ADR-0006), and sends it over the existing connection.
- The transcript is shown for the operator to confirm or retry before it is used as the question. That confirmation is the guard against invented text.
- Speech-to-text sits behind one Mac-side interface, so a cloud provider (candidates: ElevenLabs Scribe v2, Deepgram Nova-3) can replace the local model through configuration. Sending question audio to a cloud provider is allowed, but it needs an explicit setting.
- Spoken guidance (text-to-speech) is not decided here. When added, it must read the checked text verbatim (ADR-0012).

**Alternatives:**
- Cloud first: adds keys, cost, a network dependency and voice upload, with no accuracy need shown yet.
- Realtime speech-to-speech APIs: bypass the host's text checks and assume continuous conversation.

## Consequences

- `parakeet-mlx` runs on Apple Silicon only. A hosted service needs NeMo Parakeet on a GPU, or the cloud option.
- Measurement audio stays out of speech processing, and question audio stays out of measurements.
- Revisit if real-voice trials on the device fall below about +5 dB speech-to-noise, or if confirmations are often rejected.
