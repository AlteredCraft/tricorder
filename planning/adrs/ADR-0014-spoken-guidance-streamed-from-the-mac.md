# ADR-0014. Spoken guidance: the Mac speaks the checked text and streams it to the Tab5

Status: Active · Decided: 2026-09-24 · Evidence: [G-0002.01](../plans/G-0002.01-guided-ab-slice.md#observed) (`20260924-spoken-guidance` · `c039103`)

## Context

Guidance should be heard, not only read, and the device can't synthesize speech. Pocket TTS ("alba", the user's pick) runs on the Mac at about 11× real time, first audio 30–44 ms after the request. A 37-word reply is 13.4 s of 24 kHz audio, streamed over the LAN in 1.2 s.

## Decision

- The Mac synthesizes locally behind one interface (`tools/text_to_speech.py`): Pocket TTS "alba" by default, macOS `say` as fallback, off with `--tts none`. `ready.speech_output` names it, or is null.
- After acknowledging a reply, the device sends `speak{request_id}`. The Mac reads that reply's checked text verbatim (ADR-0012) on the same WebSocket: `speech_start`, `speech_chunk{offset, data}` (24 kHz mono s16, ≤ 4096 B), then `speech_end{status: complete|stopped|failed, frames}`. Once per reply, ≤ 60 s.
- The device plays from its own buffer as it receives (0.5 s prebuffer, upsampled to 48 kHz stereo). Tapping the live action or Cancel stops playback at once; the device sends `speech_stop` and reads to `speech_end`, so the next exchange starts clean. While speaking, the Mac accepts only `speech_stop` and `cancel`.
- Speech never overlaps a measurement: captures start only after `speech_end` and keep the speaker muted (ADR-0006).

**Alternatives:** whole clip before playing (seconds of silence); speech-to-speech (own words break ADR-0012); separate audio socket (another transport to secure and bound).

## Consequences

- Pocket TTS needs `tools/tts-requirements.txt` (torch). Hosting needs a server-side voice or cloud TTS behind the same interface.
- The built-in speaker is faint: guidance plays at full volume, and noise may need headphones or an external speaker.
- Revisit if speech must start before the whole reply exists (sentence-level streaming).
