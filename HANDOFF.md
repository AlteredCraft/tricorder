# Tricorder agent handoff

Updated: 2026-09-20

## Project and local workspace

- Repository: [AlteredCraft/tricorder](https://github.com/AlteredCraft/tricorder), public, MIT.
- User's checkout: `/Users/sam/Products/tricorder`.
- The project is co-developed with OpenAI Codex.
- This session aligned the starting stack, M → G → S hierarchy, artifact lifecycle guidance and decision-only ADR convention. Work remained documentation-only.
- Work in the user's local checkout. Local commits may not yet be pushed; inspect the branch and remote state before syncing.

Inspect the working tree and current branch before syncing. Fetch origin; fast-forward only when local state permits. Preserve local changes and any newer commits. Never reset the checkout to an earlier baseline.

## Read first

1. [README](README.md) for entry points and status.
2. [vision.md](vision.md) for the complete concept.
3. [Planning guidelines](planning/README.md) and its goal/spec/ADR templates.
4. [M-0001](planning/milestones.md#m-0001-validate-the-handheld-investigation), then its child [G-0001](planning/plans/G-0001-trustworthy-live-investigation.md) and the goal's five specs.
5. [Candidate native stack and research](planning/plans/G-0001.01-hardware-baseline.md#candidate-native-stack).
6. [Candidate local-instrument/service architecture](planning/plans/G-0001.04-agent-interaction.md#candidate-service-architecture).
7. The [shared run evidence format](planning/plans/G-0001.01-hardware-baseline.md#shared-run-evidence) owned by the hardware-baseline spec.

## User intent that must survive

Follow-up alignment, 2026-09-20:

- The user reports that the Tab5 is connected to this Mac. Device identity, currently running firmware and accessories have not yet been inspected.
- The user is comfortable starting with C++/ESP-IDF, LVGL and the Python service. This agrees the experiment direction; it does not establish hardware results or a final architectural choice from those results.
- Run the Python service on the Mac for early R&D, first with a scripted mock agent and then a live provider. Preserve a configurable service endpoint and provider-independent device protocol so it can later become a hosted web service; the Mac would no longer be required for conversation. Local service execution does not mean local inference. Model/speech and hosting providers remain undecided.
- The user has 25+ years of programming experience and is new to C++ and lower-level programming. Explain ownership/lifetimes, memory placement, hardware interfaces and real-time scheduling as encountered, building on their existing engineering experience.

The Tab5 is attractive and tactile. Prioritize a person holding and operating it with an agent in real time. Unattended “leave it somewhere and record” use cases are outside the initial focus.

Core loop: **Ask → measure → get feedback → adjust → discover.**

Modes: **Explore**, **Investigate**, **Compare**. Keep local readings visible and responsive throughout the conversation. The agent proposes measurements and explains evidence, while the user can interrupt, adjust or disagree.

Use all built-in sensors meaningfully over time to learn the device. This does not require every capability to run simultaneously. The factory demo's component diagram inspires an inspectable live capability view.

An initial scenario is investigating a rattling fan: camera context, spoken question, sound capture/FFT, A/B comparison, motion-assisted steadiness guidance, and spoken feedback. The IMU measures the device's movement, not a nearby object's vibration without physical coupling.

## What exists

The user moved the original detailed README into `vision.md` and created planning templates. The current guidelines/templates reflect the agreed M → G → S hierarchy and decision-only ADR convention.

This addition records:

- Candidate architectures with alternatives, source links and trade-offs in G-0001.01 and G-0001.04. The former ADR-0001/0002 proposals were reclassified into those specs; they never became decisions in force. Their files remain in Git history, their numbers are reserved, and the first actual ADR will use 0003.
- One outcome-only goal, G-0001.
- Five **Not built** specs: hardware baseline, concurrent workload, audio integrity, agent interaction, power/recovery.
- Proposed run evidence formats and measurable acceptance targets.
- A phase 1 Milestone, a README credit/navigation update, and this handoff.

There is **no firmware, backend, dependency installation, test implementation or device result**. No successful build, flashing, benchmark or sensor calibration has been established. Documentation/source inspection is the only technical evidence so far.

## Agreed starting direction; hardware validation pending

Starting stack for experiments:

- C++ application on ESP-IDF/FreeRTOS.
- LVGL 9 for the interface.
- Selected Espressif BSP and M5Unified/factory drivers, with one owner per peripheral/shared bus.
- ESP-DSP for measurements; esp_video for camera/media.
- ESP-SR for a separate speech-processing path; ESP-DL for later bounded local inference.
- Python asynchronous service on the Mac for early R&D, with FastAPI and WebSockets as initial candidates. It coordinates conversation, evidence and model/speech calls; provider credentials remain service-side. Later hosting is a separate validation scope.
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

Primary-source links and the research date are in G-0001.01's candidate-stack section. Moving documentation may change; record exact revisions during implementation.

## Next work

Use G-0001.01 to establish a reproducible hardware baseline on the connected Tab5 before a broad implementation. The starting stack and local-service-first direction have been discussed and agreed; do not repeat that decision request. Hardware bring-up does not depend on the Python service or provider selection. Apply the [planning lifecycle rules](planning/README.md#agent-lifecycle-responsibilities): assess results for architectural choices and record them in the same change, with links to the supporting goal/spec evidence. Unresolved choices remain in specs; there is no ADR proposal queue.

First inspect the Mac's available USB/serial device and installed toolchain, then identify the Tab5 and its current firmware without assuming it still runs the factory demo. Write the baseline checks before implementation, establish a recovery image and flashing instructions, and reproduce the factory demo before the native diagnostic. No device inspection or toolchain installation was performed in this session.

For each experiment, write its checks first and capture the evidence named in the spec. Append dated Observed entries; preserve refutations and incomplete runs. Revise a proposal through a dated header note before changing its hypothesis, workload or thresholds.

The numeric rates and latency limits are **proposed project targets**, not vendor specifications or measured capabilities. Revisit them openly if necessary, retaining the original results.

Bring up individual capabilities before the combined load test. Distinguish mock-agent transport timing from live-model latency. Core integration targets are camera preview, microphone capture/FFT, motion, responsive touch and wireless transfer.

## Planning conventions and verification limits

The hierarchy is M-0001 → G-0001 → its five specs, with explicit parent links; ADRs record architectural choices already made. Goal/spec files remain together in `planning/plans/`; preserve assigned IDs. The user wants to avoid document proliferation. Milestones own sequencing, specs own experiments/candidate designs, ADRs own the rationale for actual decisions, and G-0001.01 owns the shared evidence format. ADRs start Active. To revoke one, add `-R` to its identifier/filename, set it Revoked, preserve its original body and append dated goal/spec evidence explaining why, the consequences and any replacement. Update links and affected parents/summaries in the same change. The two former proposals are not revocations; no actual ADR exists yet.

All five specs have Observed set to "Not built, design only" and appear in `planning/milestones.md`, as required by the guidelines.

Local documentation checks cover file/anchor links, status consistency, preserved experiment scope and prior observations, and migrated research references. These are documentation checks only; no build, device test or remote publication is implied.

Keep API keys, personal images, recordings and run data out of the public repository. Use private/local run artifacts and link only deliberately selected publishable evidence.
