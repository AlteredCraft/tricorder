# Guided A/B operations

How to run, provision and replay the guided A/B loop. States and wire format: [guided-ab-protocol.md](guided-ab-protocol.md). The guided startup option is in the [README device notes](../README.md#device-notes).

## Running a trial

```sh
# Host service (mock; add --provider openrouter --env .env.local.openrouter for live text;
# local Parakeet and Pocket TTS "alba" by default: --stt none / --tts say|none to change)
.tools/investigation-env/bin/python -m tools.investigation_service \
  --host MAC_LAN_IP --port 8765 --output .local/runs/NEW/mock

# Serial collector (rediscover the port first; opening it can reset the Tab5)
/usr/bin/caffeinate -is .tools/python-env/bin/python -m tools.capture_serial \
  --port PORT --output .local/runs/NEW/serial --seconds 1800 \
  --spec-id G-0002.01 --spec-revision 2026-09-22 --workload 'A/B mock'

# Assess a saved session
.tools/investigation-env/bin/python -m tools.investigation_evidence .local/runs/NEW/mock/<session-dir>
```

On the device (guided startup opens this screen): **Start** (context photo, device-only) → optional **Ask** (tap, speak, **Stop**; level meter; up to 8 s) → transcript with the voice-over-background level → **Use** or **Retry** → **Record A** (steadiness label before each tap) (live spectrum) → wait for guidance → move → **Confirm position B** → **Record B** (live over A) → back at A, **Record A again** → comparison with A, B and A2 spectra overlaid. Guidance and the comparison are spoken (full volume); tapping Confirm position B stops the guidance speech, and Cancel stops the final speech without clearing the result. **Setup** holds the service address and Wi-Fi. The on-device spectra are display only: 48 log bands, 50 Hz–20 kHz, averaged 2048-point FFTs of slot 0.

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

**Upload and playback baseline (G-0001.02 C1).** Replay one saved pair repeatedly, with the guidance spoken (quiet room: it plays at full volume). The collector starts each replay after the previous one ends; the assessor needs 60 s of each stream.

```sh
.tools/investigation-env/bin/python -m tools.investigation_service --host MAC_LAN_IP --port 8765 \
  --output .local/runs/NEW/service --replay-only --replay-speech
/usr/bin/caffeinate -is .tools/python-env/bin/python -m tools.capture_serial --port PORT \
  --output .local/runs/NEW/serial --seconds 900 --reset --replay-session ab-<32hex> --replay-count 10 \
  --spec-id G-0001.02 --spec-revision 2026-09-25 --workload 'SD replay upload and playback baseline'
.tools/investigation-env/bin/python -m tools.transport_baseline_evidence .local/runs/NEW/serial \
  --service .local/runs/NEW/service
```
