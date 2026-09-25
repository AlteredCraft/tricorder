# Tricorder milestones

## M-0001: Validate the handheld investigation

**Status:** In progress.

**Scope:** One handheld A/B investigation on the Tab5 using camera, audio, motion, touch and spoken guidance, with the agent service on the Mac over the LAN. Hosted deployment is deferred.

**Deliverable:** A reproducible device build and local service that complete a guided investigation, with capability limits written down.

**Done when:** G-0001 and G-0002 are Met.

**Stack (agreed 2026-09-20):** C++/ESP-IDF 5.4.2 + LVGL 9 on the device ([ADR-0003](adrs/ADR-0003-tab5-diagnostic-foundation.md)); Python service on the Mac, mock first, then a live provider ([ADR-0010](adrs/ADR-0010-device-owned-ab-lan-experiment.md), [ADR-0012](adrs/ADR-0012-live-prose-over-verified-summaries.md)); local speech-to-text and spoken guidance on the Mac ([ADR-0013](adrs/ADR-0013-local-first-speech-to-text.md), [ADR-0014](adrs/ADR-0014-spoken-guidance-streamed-from-the-mac.md)).

### Goals

| Goal | Status | Summary |
| --- | --- | --- |
| [G-0002 One usable end-to-end investigation](plans/G-0002-thin-investigation-slice.md) | Met | Guided A/B works end to end with a live text model: spoken question, live spectrum, A/B/A-again overlay on a median level, context photo, steadiness indicator and spoken guidance. Live ratings: responsiveness 4, usefulness 3; the user judged it useful enough to harden. |
| [G-0001 A trustworthy live investigation](plans/G-0001-trustworthy-live-investigation.md) | In progress | **Priority now.** Isolated hardware baselines pass. Combined workload, agent statistics and power/recovery are open. |

Sequencing: G-0002 (usefulness) first, then harden the same code under G-0001. G-0002 does not lower G-0001's checks.

**Next:** harden the G-0002 loop under G-0001, starting with the combined workload ([G-0001.02](plans/G-0001.02-concurrent-workload.md)); the specs' Open lists hold the rest.

## Later

- Hosted agent service (device auth, TLS, credential provisioning, internet latency).
- Send the context photo and steadiness reading to the model (device-only now; not needed for the dB comparison). The user asked "What is this a picture of?" in a live loop.
- Candidate later milestones: local ESP-DL inference, full-duplex speech/AEC, wake words, higher-resolution video, USB/RS-485 peripherals, external environmental sensors.
