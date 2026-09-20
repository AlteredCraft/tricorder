# Tricorder roadmap

Date: 2026-09-20

## Phase 1: Validate the handheld investigation

These are design-only iterations. No firmware or test runner has been built, and no hardware result is implied.

| Iteration | Spec | Status | Decision informed |
| --- | --- | --- | --- |
| 1 | [Hardware baseline](../planning/plans/G-0001.01-hardware-baseline.md) | Not built | Actual panel/silicon/camera identity, peripheral ownership, reproducible versions |
| 2 | [Concurrent workload](../planning/plans/G-0001.02-concurrent-workload.md) | Not built | Rates, buffers, scheduling and memory budget |
| 3 | [Audio integrity](../planning/plans/G-0001.03-audio-integrity.md) | Not built | Raw measurement and speech-processing separation |
| 4 | [Agent interaction](../planning/plans/G-0001.04-agent-interaction.md) | Not built | Protocol, latency, cancellation and WebSocket/WebRTC choice |
| 5 | [Power and recovery](../planning/plans/G-0001.05-power-recovery.md) | Not built | Power telemetry, wake behavior and recoverable evidence |

Read the [recommendation and validation index](../planning/stack-validation.md) first. All iterations serve [G-0001](../planning/plans/G-0001-trustworthy-live-investigation.md). Accept/revise the proposed ADRs after evidence is recorded.

## Later hypotheses to write

Choose later goals from what phase 1 teaches. Candidates include local ESP-DL inference, full-duplex speech/AEC tuning, wake words, higher-resolution video, USB peripherals, RS-485 fixtures, external environmental sensors, and additional radio protocols where board/firmware support is established. Each needs a bounded hypothesis and budget; none is a committed implementation feature.
