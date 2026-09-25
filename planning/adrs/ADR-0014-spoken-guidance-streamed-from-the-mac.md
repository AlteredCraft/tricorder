# ADR-0014. Spoken guidance: the Mac speaks the checked text and streams it to the Tab5

Status: Active · Decided: 2026-09-24 · Evidence: [G-0002.01](../plans/G-0002.01-guided-ab-slice.md#observed) (`20260924-spoken-guidance`)

## Context

Guidance and comparisons should be heard, not only read. The device can't synthesize speech. Pocket TTS (voice "alba", the user's pick) runs on the Mac at about 11× real time, with the first audio 30–44 ms after the request. A 37-word reply is 13.4 s of 24 kHz audio and streamed completely over the LAN in 1.2 s.

## Decision

- The Mac synthesizes speech locally behind one interface (`tools/text_to_speech.py`): Pocket TTS "alba" by default, macOS `say` as the fallback, off with `--tts none`. `ready.speech_output` names it, or is null.
- The device asks for it: after acknowledging a reply it sends `speak{request_id}`. The Mac reads that reply's checked text verbatim (ADR-0012) and answers on the same WebSocket with `speech_start`, `speech_chunk{offset, data}` (24 kHz mono s16, ≤ 4096 B each), then `speech_end{status: complete|stopped|failed, frames}`. At most 60 s per reply, once per reply.
- The device plays while it receives (0.5 s prebuffer, upsampled to 48 kHz stereo) from its own buffer. A tap on the live action, or Cancel, stops playback at once. The device then sends `speech_stop` and reads to `speech_end`, so the next exchange starts clean. While speaking, the Mac accepts only `speech_stop` and `cancel`.
- Speech never overlaps a measurement: a capture can only start after `speech_end`, and captures keep the speaker muted (ADR-0006).

**Alternatives:** download the whole clip before playing (seconds of silence first); a speech-to-speech model (generates its own words, breaking ADR-0012); a separate audio socket (another transport to secure and bound).

## Consequences

- Pocket TTS needs `tools/tts-requirements.txt` (torch) on the Mac. A hosted service needs a server-side voice or a cloud TTS behind the same interface.
- The Tab5's built-in speaker is faint, so guidance plays at full volume. Headphones or an external speaker may be needed in noise.
- Revisit if speech must start before the whole reply text exists (sentence-level streaming from the text model).
