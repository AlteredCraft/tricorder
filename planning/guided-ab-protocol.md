# Guided A/B protocol and procedures

Reference for [G-0002.01](plans/G-0002.01-guided-ab-slice.md). Design decisions: [ADR-0010](adrs/ADR-0010-device-owned-ab-lan-experiment.md), [0011](adrs/ADR-0011-bounded-tcp-write-completion.md), [0012](adrs/ADR-0012-live-prose-over-verified-summaries.md), [0013](adrs/ADR-0013-local-first-speech-to-text.md), [0014](adrs/ADR-0014-spoken-guidance-streamed-from-the-mac.md).

## States

`idle → ready_a → recording_a → waiting → adjust → ready_b → recording_b → return_a → recording_repeat → waiting → complete`

A is where the person is; the guidance names B from their question; then they go back to A and record it again. The fixture (`planning/fixtures/G-0002.01-open-ab.json`) holds only the capture settings and a default question. SD replay resends a saved pair and skips the repeat.

Spoken ask, optional, only at `ready_a`: `ready_a → asking → transcribing → confirming → ready_a` (Use or Retry). An empty or failed transcript goes straight back to `ready_a`.

- `cancelled` (local, immediate), `offline` (disconnect) and `incomplete` (deadline) are terminal; recovery needs a fresh session ID.
- Only local buttons start captures. Late or stale replies can't advance a terminal state.
- The device reducer (`investigation_protocol.cpp`) and the host reference (`tools/investigation.py`) enforce the same rules independently.

## Wire (WebSocket text JSON, version 1)

Every message carries `version`, `type`, `boot_id`, `session_id` (IDs 1–96 chars `[A-Za-z0-9_-]`). Unknown types/fields, duplicate keys, binary frames and messages over 32 KiB are rejected, and the socket closes.

1. `hello` (+ `fixture`) → `ready{provider, speech_to_text, speech_output}`. Each is the engine name, or null when that feature is off (both are off in SD replay).
1a. Spoken ask, before capture A only, at most 5 per session: `question_start{metadata}`, `question_chunk{question_id, offset, data}` ×N, `question_end{question_id, sha256}` → `transcript{question_id, status: heard|empty|failed, text, speech_to_noise_db}`. After `heard`, the device must send `question_confirm{question_id, accepted}` before anything else except `cancel`; only an accepted transcript becomes the operator question. No per-stage ACKs.
2. `capture_start` (+ `metadata`) → `capture_ack{stage:start}`; `capture_chunk{capture_id, offset, data(base64 ≤ 4096 B)}` ×N; `capture_end{sha256}` → `capture_ack{stage:complete}`.
3. `turn{request_id, capture_ids:[A], device_ms, deadline_ms}` → `guidance{measurements, comparison:null, text}` → device `ack` → `acknowledged`.
4. Operator confirms the adjustment; capture B as in step 2. Back at A, capture A again as in step 2 (optional in the protocol; the live flow always does it).
5. `turn{capture_ids:[A,B] or [A,B,A2], adjustment}` → `comparison{comparison:{rms_delta_db = L_B − L_A, repeat_delta_db = L_A2 − L_A or null without a repeat}}` → `ack`, where L is each capture's `median_dbfs`: the median power of its 100 ms windows of slot 0 (two middle windows averaged), so brief loud moments don't decide the result. Clipping, zero RMS or a null median in any capture makes the comparison `inconclusive` (both values null). Runs saved before 2026-09-24 compared whole-capture RMS; the evidence checker reads either.
5a. Spoken guidance, after `acknowledged` for r1 (at adjust) or r2 (at complete), once per reply: `speak{request_id}` → `speech_start{request_id, format: pcm_s16le, sample_rate_hz: 24000, channels: 1}`, `speech_chunk{request_id, offset, data(base64 ≤ 4096 B)}` ×N, `speech_end{request_id, status: complete|stopped|failed, frames}`. The text is the reply's checked text, verbatim. While speaking the host accepts only `speech_stop{request_id}` (→ `speech_end{status: stopped}`; harmless after the end) and `cancel` (the stream is dropped). At most 60 s. Audio is saved as `speech/<request_id>.wav`; the transcript records a `speech_output` summary, never samples.
6. `cancel` → `cancelled`. The device stops locally without waiting for it.

Question metadata (exactly these fields): `question_id` (never a capture ID), `boot_id`, `session_id`, format `pcm_s16le`, `sample_rate_hz` 16000, `channels` 1, `frames` ≤ 128,000 (8 s), `size_bytes`, `sha256`, `source_rate_hz` 48000, `source_slot` 0, `gain_db` 24, `filter` `hpf80-lpf6500-63tap-decimate3` (the device's `SpeechFilter` on slot 0), `warmup_frames` 12000, acquisition start/end µs, `stopped_by` operator|limit, `input_clipped`, `driver_epoch_integrity`. Question audio is saved under `questions/` (with a 16 kHz WAV), never under `captures/`, and never reaches the RMS comparison or the text model. The text model gets only the confirmed text, as `operator_question` (operator context, not instructions).

Speech-to-noise (logged per ask as `question_analysis`, shown on the transcript screen): mean power of the first 200 ms (before speech) is the noise; the utterance runs from the first to the last 20 ms frame ≥ 6 dB above it; speech power is the utterance mean minus the noise. Null when no frame clears 6 dB. It reads about 1.5 dB above ADR-0013's full-band definition (80 Hz high-pass). Offline error: against speech over the noise before it, +1.0 dB bias, 2.7 dB SD (0.8 s lead-in); against the noise during speech, about 6 dB SD in café noise, because café noise level varies (`20260924-spoken-ask/offline`).

Measurement (host and device each compute it from the bytes): `frames`, `rms_counts`, `peak_counts`, `clipped_samples`, `rms_dbfs`, `median_dbfs`.

Capture metadata: format `pcm_s16le`, rate, channels, frames, requested `gain_db`, source/physical slot, size, acquisition start/end µs, `warmup_frames`, ingress block hashes, driver counters, `speaker_active:false`. **The host recomputes every measurement from the raw bytes**, and the model only writes prose.

Bounds: one connection, one transfer, one pending reply, three captures per session (A, B, A again), ≤ 1,152,000 B per capture, 900 incoming messages; separately, 5 questions of ≤ 256,000 B and 330 question messages. Transcription is bounded at 10 s (then `failed`); the device allows 30 s from the end of recording to the transcript. Device timeouts: connect 3 s, send 2 s, read 1 s, upload 30 s total, capture ACK 5 s, reply 15 s. Host idle close after 30 s between messages, or 10 min while the device waits for the operator (before Record A, while transcribing and confirming a question, at adjust, and walking back to A); ping/pong (10 s + 10 s) detects a dead device.

Capture: 48 kHz, 4 slots, s16, requested gain 24 dB, 0.5 s discarded settling prefix, then 3 s (144,000 frames) retained. Measurement slot 0 = farther mic hole.

## Running a trial

```sh
# Host service (mock; add --provider openrouter --env .env.local.openrouter for live text;
# local Parakeet and Pocket TTS "alba" by default: --stt none / --tts say|none to change)
.tools/investigation-env/bin/python -m tools.investigation_service \
  --host MAC_LAN_IP --port 8765 --output .local/runs/NEW/mock   # local Parakeet speech-to-text by default; --stt none turns it off

# Serial collector (rediscover the port first; opening it can reset the Tab5)
/usr/bin/caffeinate -is .tools/python-env/bin/python -m tools.capture_serial \
  --port PORT --output .local/runs/NEW/serial --seconds 1800 \
  --spec-id G-0002.01 --spec-revision 2026-09-22 --workload 'A/B mock'

# Assess a saved session
.tools/investigation-env/bin/python -m tools.investigation_evidence .local/runs/NEW/mock/<session-dir>
```

On the device (guided startup opens this screen): **Start** (context photo, device-only) → optional **Ask** (tap, speak, **Stop**; level meter; up to 8 s) → transcript with the voice-over-background level → **Use** or **Retry** → **Record A** (steadiness label before each tap) (live spectrum) → wait for guidance → move → **Confirm position B** → **Record B** (live over A) → back at A, **Record A again** → comparison with A, B and A2 spectra overlaid. Guidance and the comparison are spoken (full volume); tapping Confirm position B stops the guidance speech, and Cancel stops the final speech without clearing the result. **Setup** holds the service address and Wi-Fi. The on-device spectra are display only: 48 log bands, 50 Hz–20 kHz, averaged 2048-point FFTs of slot 0.

Firmware option `CONFIG_TRICORDER_GUIDED_AB_STARTUP=y` (private sdkconfig) skips automatic diagnostics at boot.

## SD provisioning, archive and download

- Provision Wi-Fi + endpoint over USB (stored in plaintext on SD, so keep the card private):
  `.tools/python-env/bin/python -m tools.provision_device --env .env.local.<net> --port PORT --endpoint ws://MAC_LAN_IP:8765/ --output .local/runs/NEW-provision`
- Every capture is saved to `/sdcard/tricorder/captures/<id>.raw/.json` after its upload's hash ACK, while the person waits anyway (for the Mac's reply, or walking back to A), and also when an upload fails (`.part` + sync + readback, metadata written last, never overwritten).
- Download and verify: `.tools/investigation-env/bin/python -m tools.download_storage --url http://DEVICE_IP --output .local/runs/NEW-download`. Only capture files are served.

## SD replay (no microphone, no operator)

Re-sends a saved A/B pair through the same upload/guidance/compare path, for transport and service testing.

```sh
.tools/investigation-env/bin/python -m tools.investigation_service --host MAC_LAN_IP --port 8765 \
  --output .local/runs/replay-NEW/mock --replay-only
/usr/bin/caffeinate -is .tools/python-env/bin/python -m tools.capture_serial --port PORT \
  --output .local/runs/replay-NEW/serial --seconds 90 --reset --replay-session ab-<32hex> \
  --checks sd_roundtrip wifi_initialize storage_http --spec-id G-0002.01 --spec-revision 2026-09-22 \
  --workload 'SD replay'
```

Replays are labeled in the UI and manifest and never count as physical trials.
