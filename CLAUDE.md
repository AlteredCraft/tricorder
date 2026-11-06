# Tricorder: agent notes

**Premise:** a handheld with a screen, touch and sensors (M5Stack Tab5) talking to an LLM, speech-to-text and text-to-speech that all run locally on the Mac, over the device's own Wi-Fi hotspot. The demo shape for every sensor: live instrument → analysis on the device → voice note → Explain. Sound is the model; the other sensors follow it. Guided investigations (Investigate tile, A/B) were dropped 2026-11-05 as not compelling to demo; their transport and service carry Explain.

Hobby project. Speed over certainty: build the feature, flash it, let the user try it. If something breaks, we fix it next time. Don't propose checks, re-runs, hardening or extra telemetry unless the user hits a problem.

- Start with [planning/milestones.md](planning/milestones.md) and the active feature's **Next**. Planning rules: [planning/README.md](planning/README.md). Ask the user only to change a feature's outcome or to mark it Done or Dropped. Everything else, proceed.
- Several changes per session are fine. Finish what the user asked for rather than stopping after one trial.
- **Tests:** write one only when it is cheaper than trying the change on the device (parsers, protocol, service logic). No tests-first rule in this repo; this overrides the global instruction. Run: `.tools/investigation-env/bin/python -m unittest discover -s tests -q`. Build: `tools/idf.sh -C firmware build`.
- **Telemetry:** log what helps debugging. Missing logs don't block or invalidate a trial; the user's report is the result. When a recording is worth keeping, `tools/capture_serial.py` writes one to private `.local/runs/YYYYMMDD-topic/`; cite it by directory name plus commit SHA.
- Device gotchas (serial reset, USB identity, provisioning, device state) are in [README.md](README.md#device-notes). Things needing the user's hands or equipment go in [TODO.md](TODO.md).
