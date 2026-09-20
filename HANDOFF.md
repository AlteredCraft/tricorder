# Tricorder agent handoff

Updated: 2026-09-20

## Project and local workspace

- Repository: [AlteredCraft/tricorder](https://github.com/AlteredCraft/tricorder), public, MIT.
- User's checkout: `/Users/sam/Products/tricorder`.
- The project is co-developed with OpenAI Codex.
- This handoff accompanies the planning-document commit. The preceding user commit was `3b005c82ccd0ef893020c1277a71799155363b83`.
- Work in the user's local checkout. The earlier remote session could not access that Mac path and committed through GitHub instead.

Inspect the working tree and current branch before syncing. Fetch origin; fast-forward only when local state permits. Preserve local changes and any newer commits. Never reset the checkout to the earlier baseline.

## Read first

1. [README](README.md) for entry points and status.
2. [vision.md](vision.md) for the complete concept.
3. [Planning guidelines](planning/README.md) and its goal/spec/ADR templates.
4. [Stack and validation index](planning/stack-validation.md).
5. [Proposed native stack ADR](planning/adrs/ADR-0001-native-firmware-stack.md).
6. [Proposed local-instrument/agent ADR](planning/adrs/ADR-0002-local-instruments-connected-agent.md).
7. [G-0001](planning/plans/G-0001-trustworthy-live-investigation.md), its five specs, and the [milestones](planning/milestones.md).

## User intent that must survive

The Tab5 is attractive and tactile. Prioritize a person holding and operating it with an agent in real time. Unattended “leave it somewhere and record” use cases are outside the initial focus.

Core loop: **Ask → measure → get feedback → adjust → discover.**

Modes: **Explore**, **Investigate**, **Compare**. Keep local readings visible and responsive throughout the conversation. The agent proposes measurements and explains evidence, while the user can interrupt, adjust or disagree.

Use all built-in sensors meaningfully over time to learn the device. This does not require every capability to run simultaneously. The factory demo's component diagram inspires an inspectable live capability view.

An initial scenario is investigating a rattling fan: camera context, spoken question, sound capture/FFT, A/B comparison, motion-assisted steadiness guidance, and spoken feedback. The IMU measures the device's movement, not a nearby object's vibration without physical coupling.

## What exists

The user moved the original detailed README into `vision.md` and created planning templates. That vision file and those guidelines/templates are preserved.

This addition records:

- Two **Proposed** ADRs with alternatives, source links, consequences and evidence gates.
- One outcome-only goal, G-0001.
- Five **Not built** specs: hardware baseline, concurrent workload, audio integrity, agent interaction, power/recovery.
- Proposed run evidence formats and measurable acceptance targets.
- A phase 1 Milestone, a README credit/navigation update, and this handoff.

There is **no firmware, backend, dependency installation, test implementation or device result**. No successful build, flashing, benchmark or sensor calibration has been established. Documentation/source inspection is the only technical evidence so far.

## Recommendation, not an accepted implementation decision

Candidate stack:

- C++ application on ESP-IDF/FreeRTOS.
- LVGL 9 for the interface.
- Selected Espressif BSP and M5Unified/factory drivers, with one owner per peripheral/shared bus.
- ESP-DSP for measurements; esp_video for camera/media.
- ESP-SR for a separate speech-processing path; ESP-DL for later bounded local inference.
- Python asynchronous service, with FastAPI and WebSockets as initial candidates.
- Evaluate WebRTC if measured continuous speech/interruption requirements warrant it.

Preserve raw measurement audio separately from enhanced speech. Noise suppression could remove the signal under investigation. Raw data still contains acoustic pickup of the device's speaker; record playback intervals.

Use capture/session/request IDs so agent statements refer to actual evidence. Local acquisition and UI must remain useful during network/model delays.

## Hardware and dependency questions

- User's demo photo says `LCD IC: ST7121`; confirm the actual panel and driver. Multiple Tab5 revisions exist.
- Identify P4 silicon revision, actual camera sensor, C6 firmware, flash/PSRAM and physical audio channels.
- The published BSP's camera naming is inconsistent with the board description; read the actual identity where supported.
- BSP battery support is not comprehensive. Verify INA226 power telemetry, charging, RTC and wake behavior separately.
- M5Unified can run directly under ESP-IDF; Arduino is not required merely to reuse that library.
- The factory demo documents IDF 5.4.2 and LVGL 9.2.2. These are reference versions, not selected final dependencies.
- P4/C6 host firmware and components must be compatible. The current Rust HAL's silicon-revision note is another reason to identify this unit before choosing Rust.
- API support and hardware acceleration do not imply simultaneous maximum throughput.

Primary-source links and the research date are in ADR-0001. Moving documentation may change; record exact revisions during implementation.

## Next work

Resume the stack discussion with the user, then use G-0001.01 to establish a reproducible hardware baseline before a broad implementation. Do not mark the Proposed ADRs Accepted merely because they are documented.

For each experiment, write its checks first and capture the evidence named in the spec. Append dated Observed entries; preserve refutations and incomplete runs. Revise a proposal through a dated header note before changing its hypothesis, workload or thresholds.

The numeric rates and latency limits are **proposed project targets**, not vendor specifications or measured capabilities. Revisit them openly if necessary, retaining the original results.

Bring up individual capabilities before the combined load test. Distinguish mock-agent transport timing from live-model latency. Core integration targets are camera preview, microphone capture/FFT, motion, responsive touch and wireless transfer.

## Planning conventions and verification limits

The current artifacts use `planning/plans/G-0001...` together, following the filename examples in the user's guidelines. The guidelines also contain older goals/specs-directory and prototype-number wording; they were not rewritten. Preserve assigned IDs and settle any future layout change explicitly.

All five specs have Observed set to "Not built, design only" and appear in `planning/milestones.md`, as required by the guidelines.

The publishing pass checks internal document links, required spec/ADR sections, status consistency and saved GitHub content. These are documentation checks only.

Keep API keys, personal images, recordings and run data out of the public repository. Use private/local run artifacts and link only deliberately selected publishable evidence.
