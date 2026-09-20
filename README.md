# Tricorder

A handheld, agent-assisted instrument for exploring the physical world with the M5Stack Tab5 (ESP32-P4).

**This project is co-developed with OpenAI Codex.**

Hold it, point it, move it, and ask questions. The goal is to learn what the device can do while a person and an agent investigate something together in real time.

## Start here

- [Vision](vision.md) — the complete product concept, interaction loop, modes and hardware roles.
- [Planning guidelines](planning/README.md) — goals, hypothesis-driven specs and architecture decision records.
- [Milestones](planning/milestones.md) — Milestone → Goal → Spec, with links to architecture decisions and validation work.
- [Agent handoff](HANDOFF.md) — current state and how to continue locally.

## Status

G-0001 is in progress, beginning with the [hardware baseline](planning/plans/G-0001.01-hardware-baseline.md#observed). The connected Tab5 identifies as ESP32-P4 revision 1.3 with 16 MB flash. Both clean factory builds booted; native diagnostics retain physical input, camera and raw audio evidence. Isolated camera/audio baselines, LAN exchanges and ten software restarts are verified. Combined workload, storage, cold-start, calibration and full-investigation acceptance remain open. The starting direction is C++/ESP-IDF with LVGL and a Python agent service on the Mac, first mocked and then provider-backed.

Run host checks with `python3 -m unittest discover -s tests -v`. Toolchains, private flash backups and run captures stay in ignored `.tools/` and `.local/` directories.

## Development

Requires Git, `uv`, and Python 3. Run `python3 tools/bootstrap.py` to install pinned vendor sources and the ESP32-P4 toolchain locally, then:

```sh
tools/idf.sh -C firmware build
.tools/python-env/bin/python -m serial.tools.list_ports -v
.tools/python-env/bin/python -m tools.capture_serial --port /dev/cu.usbmodem4 \
  --output .local/runs/diagnostic-001 --seconds 360 --reset \
  --checks imu_id ina226_manufacturer camera_driver_id rtc_advance sd_roundtrip
```

Rediscover the port after reconnecting. Flash with `tools/idf.sh -C firmware -p PORT flash` only after verifying the connected board and preserving its recovery image. Raw serial data, events and summaries are kept together in each new run directory. Missing checks remain inconclusive; these summaries do not establish full G-0001 acceptance.

Startup includes sequential 60-second camera, audio, motion and animated-display baselines, plus short live and synthetic audio fixtures. Allow at least six minutes for a full capture; this is a diagnostic build, not the final startup experience. Assess each timing capture with `python3 -m tools.camera_baseline_evidence METADATA.json`, `tools.audio_baseline_evidence`, `tools.imu_baseline_evidence`, or `tools.ui_baseline_evidence`. Camera checks count missing application buffers, motion checks retain every latest-register polling attempt, and display checks join animation state IDs to actual panel submissions. Software submission timestamps do not measure physical screen presentation. Passing isolated stages does not establish combined-load behavior. No microSD is currently installed, so `sd_roundtrip` remains inconclusive.

Capture runs also retain checked raw media in `captures/`; incomplete exports stay explicitly incomplete. Run `python3 -m tools.inspect_capture PATH_TO_CAPTURE.json` to verify bytes and create a camera PNG or per-slot WAV files (camera conversion requires `ffmpeg`). Physical channel mapping and calibration are separate checks.

The diagnostic has **Record & play** for a countdown, three-second raw recording, and four separately labeled playback slots. **Wi-Fi setup** accepts the local network name/password on the device; credentials are RAM-only. Once its address appears, run `python3 -m tools.network_probe --url http://DEVICE_IP --boot-id BOOT_ID --output .local/runs/lan-001` for three fresh echo exchanges. Audible playback, physical channel mapping and LAN round trips remain separate evidence.

**Test 10 restarts** starts a bounded software-reset sequence after the diagnostic is ready. Keep a single serial collector attached from the initial boot through completion; each boot exports camera/PCM and repeats radio initialization without joining Wi-Fi. Run `python3 -m tools.restart_evidence RUN_DIRECTORY` after capture finalization to check all ten software-reset boots. Cold starts and SD checks require their separate fixtures. Reopening the USB port can itself reset this board; `--observation-boot BOOT_ID` makes an unexpected boot explicit and does not claim continuity before attachment.

Synthetic DSP diagnostics export three repetitions of four full spectra at startup. Generate the independent desktop reference with `python3 -m tools.audio_reference --output REFERENCE_DIRECTORY`, then assess the finalized device run with `python3 -m tools.device_spectrum --reference REFERENCE_DIRECTORY --run RUN_DIRECTORY`. Regenerate the embedded PCM header with `python3 -m tools.audio_reference --header firmware/main/dsp_fixtures.generated.h`. These fixtures validate synthetic arithmetic and input immutability, not acoustic calibration or continuous acquisition.

On the Mac, prefix long serial runs with `caffeinate -is` to prevent host sleep for the collector’s lifetime. A sleeping host can lose USB events even while the battery-powered Tab5 continues running.

For a longer operator session, add `--stop-file .local/STOP` to serial capture and create that file when finished; the collector closes partials and writes its summary. Use a fresh stop-file path or remove your previous stop request before starting.

Generate synthetic desktop FFT references with `python3 -m tools.audio_reference --output .local/runs/audio-reference-001`. These use a direct DFT and explicit periodic-Hann amplitude normalization; they are preparation for device comparisons, not device DSP acceptance.

## License

[MIT](LICENSE)
