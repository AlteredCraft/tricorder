# Guided A/B protocol and procedures

Reference for [G-0002.01](plans/G-0002.01-guided-ab-slice.md). Design decisions: [ADR-0010](adrs/ADR-0010-device-owned-ab-lan-experiment.md), [0011](adrs/ADR-0011-bounded-tcp-write-completion.md), [0012](adrs/ADR-0012-live-prose-over-verified-summaries.md).

## States

`idle → ready_a → recording_a → waiting → adjust → ready_b → recording_b → waiting → complete`

- `cancelled` (local, immediate), `offline` (disconnect) and `incomplete` (deadline) are terminal; recovery needs a fresh session ID.
- Only local buttons start captures. Late or stale replies can't advance a terminal state.
- The device reducer (`investigation_protocol.cpp`) and the host reference (`tools/investigation.py`) enforce the same rules independently.

## Wire (WebSocket text JSON, version 1)

Every message carries `version`, `type`, `boot_id`, `session_id` (IDs 1–96 chars `[A-Za-z0-9_-]`). Unknown types/fields, duplicate keys, binary frames and messages over 32 KiB are rejected, and the socket closes.

1. `hello` (+ `fixture`) → `ready`.
2. `capture_start` (+ `metadata`) → `capture_ack{stage:start}`; `capture_chunk{capture_id, offset, data(base64 ≤ 4096 B)}` ×N; `capture_end{sha256}` → `capture_ack{stage:complete}`.
3. `turn{request_id, capture_ids:[A], device_ms, deadline_ms}` → `guidance{measurements, comparison:null, text}` → device `ack` → `acknowledged`.
4. Operator confirms the adjustment; capture B as in step 2.
5. `turn{capture_ids:[A,B], adjustment}` → `guidance{comparison:{rms_delta_db = 20·log10(RMS_B/RMS_A)}}` → `ack`. Clipping or zero RMS makes the comparison `inconclusive`.
6. `cancel` → `cancelled`. The device stops locally without waiting for it.

Capture metadata: format `pcm_s16le`, rate, channels, frames, requested `gain_db`, source/physical slot, size, acquisition start/end µs, `warmup_frames`, ingress block hashes, driver counters, `speaker_active:false`. **The host recomputes every measurement from the raw bytes**, and the model only writes prose.

Bounds: one connection, one transfer, one pending reply, two captures per session, ≤ 1,152,000 B per capture, 640 incoming messages. Device timeouts: connect 3 s, send 2 s, read 1 s, upload 30 s total, capture ACK 5 s, reply 15 s. Host idle close after 30 s between messages, or 10 min while the device waits for the operator (before Record A, and at adjust); ping/pong (10 s + 10 s) detects a dead device.

Capture: 48 kHz, 4 slots, s16, requested gain 24 dB, 0.5 s discarded settling prefix, then 3 s (144,000 frames) retained. Measurement slot 0 = farther mic hole.

## Running a trial

```sh
# Host service (mock; add --provider openrouter --env .env.local.openrouter for live text)
.tools/investigation-env/bin/python -m tools.investigation_service \
  --host MAC_LAN_IP --port 8765 --output .local/runs/NEW/mock

# Serial collector (rediscover the port first; opening it can reset the Tab5)
/usr/bin/caffeinate -is .tools/python-env/bin/python -m tools.capture_serial \
  --port PORT --output .local/runs/NEW/serial --seconds 1800 \
  --spec-id G-0002.01 --spec-revision 2026-09-22 --workload 'A/B mock'

# Assess a saved session
.tools/investigation-env/bin/python -m tools.investigation_evidence .local/runs/NEW/mock/<session-dir>
```

On the device (guided startup opens this screen): **Start** → **Record A** (live spectrum) → wait for guidance → move → **Confirm position B** → **Record B** (live over A) → comparison with A/B spectra overlaid. **Setup** holds the service address and Wi-Fi. The on-device spectra are display only: 48 log bands, 50 Hz–20 kHz, averaged 2048-point FFTs of slot 0.

Firmware option `CONFIG_TRICORDER_GUIDED_AB_STARTUP=y` (private sdkconfig) skips automatic diagnostics at boot.

## SD provisioning, archive and download

- Provision Wi-Fi + endpoint over USB (stored in plaintext on SD, so keep the card private):
  `.tools/python-env/bin/python -m tools.provision_device --env .env.local.<net> --port PORT --endpoint ws://MAC_LAN_IP:8765/ --output .local/runs/NEW-provision`
- Every capture is saved to `/sdcard/tricorder/captures/<id>.raw/.json` before upload (`.part` + sync + readback, metadata written last, never overwritten).
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
