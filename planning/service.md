# Mac service

The Mac side of Explain: one WebSocket session per Explain, in which the device sends an instrument's analysis, a local text model writes a reading of it, and the Mac speaks the reading back. Decisions behind it: [ADR-0011](adrs/ADR-0011-bounded-tcp-write-completion.md) (writes), [0012](adrs/ADR-0012-live-prose-over-verified-summaries.md) (prose over checked numbers), [0013](adrs/ADR-0013-local-first-speech-to-text.md) (speech-to-text), [0014](adrs/ADR-0014-spoken-guidance-streamed-from-the-mac.md) (spoken replies).

It grew out of the guided A/B investigation, dropped 2026-11-05. The A/B states, captures, fixtures and SD replay were removed in [#6](https://github.com/AlteredCraft/tricorder/issues/6).

## Run it

```sh
.tools/investigation-env/bin/python -m tools.service --output .local/runs/NEW --provider local
```

- `--provider local` (Ollama at `http://127.0.0.1:11434/v1`, model `gemma4:latest`; `--model`, `--base-url` change them), `mock` (scripted text, the default), or `openrouter` / `openai` with `--env .env.local.<name>` for the key.
- `--tts pocket` (default, Pocket TTS voice "alba"), `say` (macOS) or `none`. `--stt parakeet` (default) or `none`.
- Listens on `ws://0.0.0.0:8765` (`--host`, `--port`). Only peers on a private network or this Mac are accepted, one device at a time.
- Each session writes `<output>/<boot_id>-<session_id>/`: `manifest.json`, `transcript.jsonl` (every message except media), `photos/`, `questions/` and `speech/` (WAV).

## Where the code is

| Side | Files |
| --- | --- |
| Device | `firmware/main/service_client.cpp` (session, upload, playback), `service_protocol.cpp` (message checks), `service_wire.h` (address, frame reassembly), `speech_stream.h`, `voice_note.cpp` |
| Mac | `tools/service.py` (session), `tools/service_protocol.py` (shared rules, voice note, number check), `tools/<kind>_explain.py` per instrument, `tools/openai_provider.py`, `tools/speech_to_text.py`, `tools/text_to_speech.py` |

## Wire (WebSocket text JSON, version 1)

Every message carries `version`, `type`, `boot_id`, `session_id` (IDs are 1–96 characters of `[A-Za-z0-9_-]`). Unknown types or fields, duplicate keys, binary frames and messages over 32 KiB are rejected and the socket closes. The device opens a new session, with a fresh session ID, for each Explain.

1. `hello` → `ready{provider, speech_to_text, speech_output}`. Each is an engine name, or null when that feature is off.
2. Voice note, optional, before the explain, at most 5 per session: `question_start{metadata}`, `question_chunk{question_id, offset, data}` ×N, `question_end{question_id, sha256}` → `transcript{question_id, status: heard|empty|failed, text, speech_to_noise_db}`. After `heard`, the device must send `question_confirm{question_id, accepted}` before anything else. An accepted transcript reaches the Sound prompt as `voice_note`. No instrument records a note today; the path is kept for the voice demo.
3. Camera only: `photo_chunk{request_id, offset, data}` ×N (JPEG, at most 512 KiB), in order, before its explain.
4. `analysis_explain{request_id, analysis}` → `analysis_reply{request_id, text}`, or `incomplete{reason}` when the model failed, timed out or its text was refused. Once per session.
5. `speak{request_id}` → `speech_start{request_id, format: pcm_s16le, sample_rate_hz: 24000, channels: 1}`, `speech_chunk{request_id, offset, data}` ×N, `speech_end{request_id, status: complete|stopped|failed, frames}`. The text is the reply's, verbatim. While it plays the host accepts only `speech_stop{request_id}` (harmless after the end). At most 60 s.

All `data` is base64 of at most 4096 bytes.

**Analysis.** `analysis.kind` is `sound` (also when missing), `motion`, `power` or `camera`. Each `tools/<kind>_explain.py` validates the fields, builds what the model sees and checks the reply: ASCII the device font can draw, at most 2048 bytes, and for sound, motion and power no number with a unit that the analysis doesn't contain (rounding allowed, ADR-0012). The model gets only the analysis numbers, plus the photo for camera.

**Question metadata** (exactly these fields): `question_id`, `boot_id`, `session_id`, format `pcm_s16le`, `sample_rate_hz` 16000, `channels` 1, `frames` ≤ 128,000 (8 s), `size_bytes`, `sha256`, `source_rate_hz` 48000, `source_slot` 0, `gain_db` 24, `filter` `hpf80-lpf6500-63tap-decimate3`, `warmup_frames` 12000, acquisition start/end µs, `stopped_by` operator|limit, `input_clipped`, `driver_epoch_integrity`.

**Speech-to-noise** (sent with the transcript, logged as `question_analysis`): the mean power of the first 200 ms is the noise; the utterance runs from the first to the last 20 ms frame at least 6 dB above it; speech power is the utterance mean minus the noise. Null when no frame clears 6 dB.

## Bounds

- Device: connect 3 s, each send 10 s, `ready` within 15 s, transcript within 30 s of the upload, reply within 45 s, speech within 90 s.
- Mac: transcription 10 s (then `failed`), model 30 s, idle close 30 s between messages, or 10 min while a transcript waits for the person or the reply is playing. Ping/pong (10 s + 10 s) detects a dead device.
- One connection, one explain per session, 32 session directories per `--output`.

## Provisioning

Wi-Fi and the service address load from the SD card at boot (plaintext, so keep the card private).

```sh
.tools/python-env/bin/python -m tools.provision_device --env .env.local.<net> --port PORT \
  --endpoint ws://MAC_LAN_IP:8765/ --output .local/runs/NEW-provision
```

- **Hotspot mode** (F-0003): an env file with `WIFI_MODE=ap` and no `--endpoint`. The device broadcasts the network; the Mac joins it, and the device takes the service address from the Mac's lease. Offline, so run the service with `--provider local`.
- **Known networks** (F-0008): add `--known .env.local.<name>` (up to 4) for one-tap joins in the Wi-Fi dialog.
- The ops TUI (`uv run tools/ops.py`) does the same and checks the Mac can reach the device.
