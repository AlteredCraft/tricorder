# Tricorder milestones

## M-0002: Sensors, explained by a local LLM

**Status:** In progress

**Theme:** The person picks up the Tricorder, opens a sensor instrument from the start screen, and asks the LLM on the Mac about what it measured. Everything runs locally: the device's own hotspot, Ollama, Parakeet, Pocket TTS. Sound is the first instrument and the template for the rest.

**Retargeted 2026-11-05 (user):** the Investigate tile (guided A/B) is dropped as not compelling to demo. The Sound tile stays. The premise is now the device, its screen, touch and sensors, connected to an LLM running locally on the Mac.

**Active:** Setup copy and known networks ([#9](https://github.com/AlteredCraft/tricorder/issues/9), F-0008 built, awaiting its first trial); then A/B code removal ([#6](https://github.com/AlteredCraft/tricorder/issues/6)).

| Feature | Status |
| --- | --- |
| [F-0001 Start screen](features/F-0001-start-screen.md) | Done |
| [F-0002 Sound session analysis](features/F-0002-sound-analysis.md) | Done |
| [F-0003 Device hotspot and local text model](features/F-0003-device-hotspot.md) | Done (Explain over the hotspot; A/B part dropped) |
| [F-0004 Start screen for the demo](features/F-0004-demo-start-screen.md) ([#2](https://github.com/AlteredCraft/tricorder/issues/2)) | Done |
| [F-0005 Motion](features/F-0005-motion.md) ([#3](https://github.com/AlteredCraft/tricorder/issues/3)) | Done |
| [F-0006 Camera](features/F-0006-camera.md) ([#4](https://github.com/AlteredCraft/tricorder/issues/4)) | Done 2026-11-07 |
| [F-0007 Power](features/F-0007-power.md) ([#5](https://github.com/AlteredCraft/tricorder/issues/5)) | Done 2026-11-09 |
| [F-0008 Setup copy and known networks](features/F-0008-setup-known-networks.md) ([#9](https://github.com/AlteredCraft/tricorder/issues/9)) | In progress |


## M-0001: Validate the handheld investigation

**Status:** Done

**Scope:** One handheld A/B investigation on the Tab5 using camera, audio, motion, touch and spoken guidance, with the agent service on the Mac over the LAN. Hosted deployment is deferred.

**Deliverable:** A reproducible device build and local service that complete a guided investigation, with capability limits written down.

**Done when:** G-0001 and G-0002 are Met.

**Stack (agreed 2026-09-20):** C++/ESP-IDF 5.4.2 + LVGL 9 on the device ([ADR-0003](adrs/ADR-0003-tab5-diagnostic-foundation.md)); Python service on the Mac, mock first, then a live provider ([ADR-0010](adrs/ADR-0010-device-owned-ab-lan-experiment.md), [ADR-0012](adrs/ADR-0012-live-prose-over-verified-summaries.md)); local speech-to-text and spoken guidance on the Mac ([ADR-0013](adrs/ADR-0013-local-first-speech-to-text.md), [ADR-0014](adrs/ADR-0014-spoken-guidance-streamed-from-the-mac.md)).

**Closed:** 2026-09-26, both goals Met; G-0001 with reduced scope (user-approved). Lesson: the goals were too large (over a week) and checks ran ahead of product use. The guided A/B it produced was dropped 2026-11-05 as not compelling to demo; its service, transport and speech path carry Explain.

| Goal | Status |
| --- | --- |
| [G-0002 One usable end-to-end investigation](plans/G-0002-thin-investigation-slice.md) | Met |
| [G-0001 A trustworthy live investigation](plans/G-0001-trustworthy-live-investigation.md) | Met |

## Later

Ideas, none scheduled. Dropped 2026-11-05 as verification rather than demo work: SD event log, battery power profiles, SD power loss mid-save.

- Sleep and wake: screen-off on idle and touch wake.
- Speech overlapping a live measurement (full-duplex, AEC); wake words.
- External environmental sensors over the Tab5 ExtPort2 pigtail ([#10](https://github.com/AlteredCraft/tricorder/issues/10)); USB/RS-485 peripherals.
- Hosted service instead of the Mac (device auth, TLS, credential provisioning, internet latency).
