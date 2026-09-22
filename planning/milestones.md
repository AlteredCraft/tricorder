# Tricorder milestones

Date: 2026-09-20

## M-0001: Validate the handheld investigation

**Status:** In progress; implementation resumed at the user's request on 2026-09-21. Prioritize G-0002's thin slice, then harden the same implementation under G-0001; see [HANDOFF.md](../HANDOFF.md).

**Scope:** One trustworthy handheld A/B investigation using built-in camera, audio, motion, touch and spoken guidance, with the agent service on the Mac over the local network. Hosted deployment is deferred.

**Deliverable:** A reproducible device build and local service, with run evidence for a complete guided investigation and explicitly recorded capability limits.

**Completion:** G-0001's outcome is Met with linked run evidence; required capability, concurrency, audio, interaction and recovery checks are resolved; architectural choices actually made are recorded in evidence-backed ADRs, and any revoked decisions are identified with their consequences addressed. Missing evidence or unresolved required choices/failures prevents completion. Scope changes preserve the original result through dated revisions. G-0002 adds an early usable-loop outcome whose checks must also be satisfied; its success alone cannot complete this milestone or waive any G-0001 requirement.

Hardware baseline execution has begun. Device capability and end-to-end acceptance remain unverified.

The user has agreed to start with C++/ESP-IDF, LVGL and a Python agent service. For iteration 4, run the service on the user's Mac over the local network, first with a scripted mock agent and then a live provider. The service endpoint is configurable for future hosting; deployment to the internet is outside this milestone.

### G-0001: A trustworthy live investigation

**Goal:** [G-0001](plans/G-0001-trustworthy-live-investigation.md) — In progress. The specs below are children of this goal; the order is a starting sequence, with dependencies stated separately.

| Order | Spec | Status | Depends on | Decision informed |
| --- | --- | --- | --- | --- |
| 1 | [Hardware baseline](plans/G-0001.01-hardware-baseline.md) | In progress | None | Actual panel/silicon/camera identity, peripheral ownership, reproducible versions |
| 2 | [Concurrent workload](plans/G-0001.02-concurrent-workload.md) | In progress (camera/JPEG/preview passes; combined work open) | .01 | Rates, buffers, scheduling and memory budget |
| 3 | [Audio integrity](plans/G-0001.03-audio-integrity.md) | In progress (isolated live integrity) | .01; repeat under .02 load | Raw measurement and speech-processing separation |
| 4 | [Agent interaction](plans/G-0001.04-agent-interaction.md) | In progress (shared mock under G-0002) | .02, .03 | Protocol, latency, cancellation and WebSocket/WebRTC choice |
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

**Progress — motion baseline.** 2026-09-20: [.02](plans/G-0001.02-concurrent-workload.md#observed) verifies the 100 Hz motion baseline with checked driver errors and passes camera/audio regressions. UI/network/concurrent work and operator follow-ups remain open.

**Progress — animated display.** 2026-09-20: [.02](plans/G-0001.02-concurrent-workload.md#observed) verifies 30.30 fps panel submission with passing interval limits and clean camera/audio/motion regressions. Original failed UI evidence is retained. JPEG/network, combined and operator gates remain open.

**Progress — stopping checkpoint.** 2026-09-20: [.02](plans/G-0001.02-concurrent-workload.md#observed) camera+JPEG candidate builds and decodes 30 images but fails camera completion accounting; 98 host tests pass. Failed evidence is retained, later sustained stages are inconclusive, and all host work has stopped. Next: fix camera buffer hold/completion accounting, then repeat regressions. [HANDOFF.md](../HANDOFF.md) records the exact checkpoint; [TODO.md](../TODO.md) lists user follow-ups. No remaining gate is waived.

**Progress — camera/JPEG regression resolved.** 2026-09-21: [.02](plans/G-0001.02-concurrent-workload.md#observed) passes 30 fps ordered acquisition, 30 fresh JPEG decodes and all sequential/live/synthetic regressions after retaining a four-buffer ordering failure. 103 host tests and P4 compilation pass. [ADR-0007](adrs/ADR-0007-bounded-camera-fifo.md) records the bounded ring/FIFO decision. JPEG queued-timeout ownership needs fault-injection work before preview/concurrency; all combined, storage, interaction and power gates remain open.

**Progress — JPEG error-path protection verified.** 2026-09-21: [.02](plans/G-0001.02-concurrent-workload.md#observed) verifies fail-stop before queued-JPEG error-path unwinding with a user-approved controlled fault, separately retaining the failed ordinary run. Normal firmware is restored and passes all sequential/live/synthetic regressions;112 host tests pass. [ADR-0008](adrs/ADR-0008-jpeg-error-path-fail-stop.md) records the bounded policy. Preview/concurrency, device memory-return and every original full-investigation gate remain open.

**Progress — live preview verified.** 2026-09-21: [.02](plans/G-0001.02-concurrent-workload.md#observed) retains all native camera frames with an owned half-rate preview and30 JPEGs, preserving the two failed scheduling/startup comparisons. All sequential/live/synthetic regressions and121 host tests pass. [ADR-0009](adrs/ADR-0009-owned-preview-and-render-placement.md) records buffer ownership and core1 rendering. Full simultaneous workloads, host backpressure, device memory return and every original investigation/operator gate remain open.

### G-0002: One usable end-to-end investigation

**Goal:** [G-0002](plans/G-0002-thin-investigation-slice.md) — In progress; fresh physical mock trial and two live text summary probes pass; speech and full acceptance incomplete.

**Serving spec:** [G-0002.01 Guided A/B vertical slice](plans/G-0002.01-guided-ab-slice.md) — In progress; device integration built, physical/live acceptance open.

**Sequence and ownership:** G-0001 and G-0002 are sibling goals under M-0001. Reuse the verified G-0001 foundation to build G-0002's mock-then-live ask → measure → feedback → adjust → compare loop next. Then harden that same implementation under G-0001's five unchanged specs. G-0002 does not inherit or reparent .04, lower its thresholds, or require finishing every diagnostic before its bounded experiment. G-0001 remains the full trustworthy-product acceptance goal.

**Progress — 2026-09-21, planning only:** User requested the vertical slice to validate usefulness earlier. New goal/spec record its bounded checks and the handback to reliability work. No code, hardware run, architectural adoption or acceptance result is added. Prior G-0001 progress and failed evidence remain unchanged.

**Progress — 2026-09-21, G-0002 resumed:** Tests-first host protocol/evidence reducer, bounded WebSocket mock service and collector metadata are implemented. The operator selected a steady speaker fixture. Synthetic host and loopback tests do not count as physical or live-provider acceptance; all G-0001 gates remain unchanged. See the [checkpoint](guided-ab-protocol.md).

## Later hypotheses to write

A hosted agent-service experiment should test the same device protocol against an internet-accessible deployment without requiring the Mac. Define device authentication, encrypted transport, credential provisioning, capture retention and internet latency/recovery checks before implementation. Hosting and model providers remain open choices.

Choose later milestones and their goals from what M-0001 teaches, then write specs under those goals. Candidates include local ESP-DL inference, full-duplex speech/AEC tuning, wake words, higher-resolution video, USB peripherals, RS-485 fixtures, external environmental sensors, and additional radio protocols where board/firmware support is established. Each needs a bounded hypothesis and budget; none is a committed implementation feature.


**Progress — 2026-09-21, G-0002 device integration:** [G-0002.01](plans/G-0002.01-guided-ab-slice.md#observed) now has a compiled/booted device client and manual A/B flow, with 168 passing host tests. Operator trials are being prepared. No physical A/B or live-provider acceptance is established, and G-0001's thresholds and earlier evidence remain unchanged.


**Progress — 2026-09-21, first physical G-0002 exchange:** The on-device loop completes with verified raw evidence/ACK joins, but startup transients refute the steady-tone interpretation. The failed run is preserved; an explicit settling-prefix correction is built/flashed with 172 passing tests and awaits a repeat. [ADR-0010](adrs/ADR-0010-device-owned-ab-lan-experiment.md) records the bounded mock architecture, not acoustic/live acceptance. No G-0001 gate or parent goal is completed.


**Disposition — 2026-09-21:** The user paused remaining G-0002 physical trials because of an outdoor lawnmower and separately deferred live-provider work. All host trial processes are stopped. Resume the remaining mock repeats/failure checks and fixture characterization when requested in stable conditions. G-0002, G-0001 and M-0001 remain incomplete; acceptance requirements are unchanged.


**Progress — 2026-09-21, physical work resumed:** The user reports mowing stopped and completed two additional corrected mock loops. Three developmental loops now pass technical evidence checks; fixture characterization and controlled failure checks remain. Live-provider work is still deferred. No parent goal or full G-0001 gate is complete.


**Progress — 2026-09-21, mock trial closeout:** G-0002 now retains three corrected developmental loops, delayed/cancelled reply evidence, and a controlled service outage followed by fresh recording/guidance and successful cancellation. All trial processes are stopped. Fixture and timing limits remain explicit; serial attachment failures are preserved. Live-provider/speech/usefulness work is deferred; no parent goal or full G-0001 gate is complete.

**Progress — 2026-09-22, four-stage continuation:** User resumed transport diagnosis, fresh physical verification, OpenAI live speech/guidance and original G-0001 hardening. G-0002 remains In progress. The earlier live deferral is superseded; acceptance still requires all original physical, live, usefulness, concurrency, storage and power evidence.


**Progress — 2026-09-22, commit checkpoint:** bounded TCP completion passes native tests and normal SD replay; a fresh physical mock loop completes (B/A −3.89 dB), while the prior B failure's cause remains unproven. Two approved OpenRouter text calls pass over stored evidence summaries. 192 host tests and P4 build/flash pass. [ADR-0011](adrs/ADR-0011-bounded-tcp-write-completion.md) and [ADR-0012](adrs/ADR-0012-live-prose-over-verified-summaries.md) record the bounded decisions. Speech, three rated live loops, formal fixture/timing gaps and all remaining G-0001 gates stay open. Trial processes are stopped; no milestone is complete.
