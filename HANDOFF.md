# Handoff

Updated 2026-09-22. Current state and how to resume. History is in git and in the specs' Observed sections.

## State

- **Working:** Guided A/B on the Tab5. Record A → Mac service guidance → move → Record B → comparison, with local cancel, offline/incomplete states, SD archive before upload, and SD replay. Mock and OpenRouter text providers ([G-0002.01](planning/plans/G-0002.01-guided-ab-slice.md)).
- **Verified in isolation:** camera 30 fps + JPEG + owned preview, 48 kHz 4-slot audio with FFT and speech path, IMU 100 Hz, 30 fps UI, SD, Wi-Fi, ten software resets ([G-0001](planning/plans/G-0001-trustworthy-live-investigation.md)).
- **Not built:** instrument-style UI (the A/B screen is a text label plus buttons; spectrum and preview exist only in diagnostics), speech in/out, combined workload, power/recovery.
- **Unresolved:** one historical B-upload failure. Short TCP writes are now fixed, but that failure wasn't reproduced ([ADR-0011](planning/adrs/ADR-0011-bounded-tcp-write-completion.md)).
- Flashed firmware = `71aebd5` content with `CONFIG_TRICORDER_GUIDED_AB_STARTUP=y`. 192 host tests pass.

## Next (proposed 2026-09-22; confirm with user before starting)

1. **Instrument UI for Guided A/B** from existing parts: live spectrum while recording, A/B spectra overlaid in the comparison, camera context shot, IMU steadiness indicator. Move Wi-Fi/endpoint setup off the main flow.
2. **Stop physical 1000 Hz reruns for plumbing.** Test transport with SD replay plus injected faults. For acoustic checks, use broadband noise or a real object; the tone varied from −10 to +1 dB because of room reflections.
3. Choose a speech provider and add spoken ask/guidance.
4. Three operator-rated live loops (G-0002.01 check 4).
5. Then G-0001 hardening: combined workload, statistics, power.

## Device and environment

- Tab5 USB serial **E8:F6:0A:E2:E0:0E** (last `/dev/cu.usbmodem1101`; `/dev/cu.usbmodem11101` is a different board). Rediscover with `.tools/python-env/bin/python -m serial.tools.list_ports -v`.
- **Opening the serial port can reset the Tab5.** Keep one collector open for a whole trial. Prefix long runs with `/usr/bin/caffeinate -is`, because Mac sleep drops USB data.
- Wi-Fi and endpoint load from SD at boot (provisioned from `.env.local.newnet`). Last IPs: Mac `192.168.0.44`, Tab5 `192.168.0.66`; recheck before use.
- Secrets: `.env.local.*` (Wi-Fi, OpenRouter key) and the SD card (plaintext Wi-Fi). Never print or commit them.
- Private evidence: `.local/runs/`. Flash backups and recovery steps: `.local/runs/20260920-baseline/RECOVERY.md`.
- Battery and microSD are installed.

## Commands

```sh
python3 tools/bootstrap.py                                          # toolchain + pinned vendor sources
tools/idf.sh -C firmware build                                      # P4 build
tools/idf.sh -C firmware -p PORT flash                              # after confirming USB identity
.tools/investigation-env/bin/python -m unittest discover -s tests -q # host tests
```

Trial, provisioning and replay commands: [guided-ab-protocol.md](planning/guided-ab-protocol.md). USB, localhost listeners and builds may need sandbox escalation.
