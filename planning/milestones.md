# Tricorder milestones

Date: 2026-09-20

## M-0001: Validate the handheld investigation

**Status:** In progress; G-0001 hardware baseline started.

**Scope:** One trustworthy handheld A/B investigation using built-in camera, audio, motion, touch and spoken guidance, with the agent service on the Mac over the local network. Hosted deployment is deferred.

**Deliverable:** A reproducible device build and local service, with run evidence for a complete guided investigation and explicitly recorded capability limits.

**Completion:** G-0001's outcome is Met with linked run evidence; required capability, concurrency, audio, interaction and recovery checks are resolved; architectural choices actually made are recorded in evidence-backed ADRs, and any revoked decisions are identified with their consequences addressed. Missing evidence or unresolved required choices/failures prevents completion. Scope changes preserve the original result through dated revisions.

Hardware baseline execution has begun. Device capability and end-to-end acceptance remain unverified.

The user has agreed to start with C++/ESP-IDF, LVGL and a Python agent service. For iteration 4, run the service on the user's Mac over the local network, first with a scripted mock agent and then a live provider. The service endpoint is configurable for future hosting; deployment to the internet is outside this milestone.

### G-0001: A trustworthy live investigation

**Goal:** [G-0001](plans/G-0001-trustworthy-live-investigation.md) — In progress. The specs below are children of this goal; the order is a starting sequence, with dependencies stated separately.

| Order | Spec | Status | Depends on | Decision informed |
| --- | --- | --- | --- | --- |
| 1 | [Hardware baseline](plans/G-0001.01-hardware-baseline.md) | In progress | None | Actual panel/silicon/camera identity, peripheral ownership, reproducible versions |
| 2 | [Concurrent workload](plans/G-0001.02-concurrent-workload.md) | In progress (isolated baselines) | .01 | Rates, buffers, scheduling and memory budget |
| 3 | [Audio integrity](plans/G-0001.03-audio-integrity.md) | In progress (isolated live integrity) | .01; repeat under .02 load | Raw measurement and speech-processing separation |
| 4 | [Agent interaction](plans/G-0001.04-agent-interaction.md) | Not built | .02, .03 | Protocol, latency, cancellation and WebSocket/WebRTC choice |
| 5 | [Power and recovery](plans/G-0001.05-power-recovery.md) | Not built | .01; repeat with .02/.04 | Power telemetry, wake behavior and recoverable evidence |

**Architecture under investigation:** The [hardware-baseline spec](plans/G-0001.01-hardware-baseline.md#candidate-native-stack) owns the native-stack research; the [agent-interaction spec](plans/G-0001.04-agent-interaction.md#candidate-service-architecture) owns the device/service candidates. [ADR-0003](adrs/ADR-0003-tab5-diagnostic-foundation.md) records the reproduced diagnostic foundation; broader choices remain under investigation. The [hardware-baseline spec](plans/G-0001.01-hardware-baseline.md#shared-run-evidence) also owns the shared evidence format.

**Progress — 2026-09-20:** Planning only. Established M-0001 → G-0001 → five specs; no implementation evidence. Next action is the hardware baseline. Review ADR-0001 when that experiment records an outcome, including a partial or refuted result.

**Progress — 2026-09-20, ADR reconciliation:** The two former proposals were moved into the specs above; their IDs remain reserved in history. The earlier instruction to review ADR-0001 is replaced by assessing .01's results for architectural choices and recording an ADR only when a choice is made from that evidence. Scope, completion outcomes and test thresholds are unchanged.

**Progress — 2026-09-20, hardware bring-up:** [.01](plans/G-0001.01-hardware-baseline.md#observed): verified recovery reads, two factory builds booted, native identity/RTC checks running. Physical fixtures, SD (card absent), functional captures/network and later specs remain open. [ADR-0003](adrs/ADR-0003-tab5-diagnostic-foundation.md) records the diagnostic foundation.

**Progress — media:** 2026-09-20: [.01](plans/G-0001.01-hardware-baseline.md#observed) now retains a readable camera frame and hash-verified raw PCM. Acoustic/network/restart checks and SD-dependent gates remain open; [ADR-0004](adrs/ADR-0004-capture-completion.md) records capture completion.

**Progress — interactive diagnostics.** 2026-09-20: Audible but faint playback recorded; physical slot mapping remains unresolved. Radio startup corrected and Wi-Fi setup prepared; LAN evidence, storage and restart gates remain open. See [.01](plans/G-0001.01-hardware-baseline.md#observed) and [ADR-0005](adrs/ADR-0005-diagnostic-radio-startup.md).

**Progress — LAN verified.** 2026-09-20: [.01](plans/G-0001.01-hardware-baseline.md#observed) records three matched LAN round trips and recognizable raw-slot 0/2 playback. Headphone/physical mapping, storage and restart gates remain open.

**Progress — headphones and software resets.** 2026-09-20: [.01](plans/G-0001.01-hardware-baseline.md#observed) confirms both-ear headphone playback and ten software-reset boots after a display-lock correction. Cold starts, microphone mapping, storage and later gates remain open.

**Progress — device DSP.** 2026-09-20: [.03](plans/G-0001.03-audio-integrity.md#observed) passes twelve on-device synthetic FFT comparisons. Speech separation, continuous acquisition, acoustic/load and SD checks remain open.

**Progress — speech replay.** 2026-09-20: [.03](plans/G-0001.03-audio-integrity.md#observed) verifies synthetic raw/speech separation on P4. Live ingress checks are prepared; microphone mapping remains ambiguous. Required hardware, load, interaction and recovery gates remain open.

**Progress — live audio boundary.** 2026-09-20: [.03](plans/G-0001.03-audio-integrity.md#observed) verifies three live raw/speech pairs; [ADR-0006](adrs/ADR-0006-raw-audio-and-derived-speech.md) records immutable raw input and separately owned derivatives. [.02](plans/G-0001.02-concurrent-workload.md#observed) has a built sustained-audio diagnostic; combined workload and other required gates remain open.

**Progress — isolated baselines.** 2026-09-20: [.02](plans/G-0001.02-concurrent-workload.md#observed) passes a native 30 fps camera baseline and two 60-second audio baselines. Combined workload, UI/network stages and remaining hardware/interaction/recovery gates stay open. Operator follow-ups are listed in [TODO.md](../TODO.md).

## Later hypotheses to write

A hosted agent-service experiment should test the same device protocol against an internet-accessible deployment without requiring the Mac. Define device authentication, encrypted transport, credential provisioning, capture retention and internet latency/recovery checks before implementation. Hosting and model providers remain open choices.

Choose later milestones and their goals from what M-0001 teaches, then write specs under those goals. Candidates include local ESP-DL inference, full-duplex speech/AEC tuning, wake words, higher-resolution video, USB peripherals, RS-485 fixtures, external environmental sensors, and additional radio protocols where board/firmware support is established. Each needs a bounded hypothesis and budget; none is a committed implementation feature.
