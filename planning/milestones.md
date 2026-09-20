# Tricorder milestones

Date: 2026-09-20

## M-0001: Validate the handheld investigation

**Status:** Not started, derived from G-0001 and its unbuilt specs.

**Scope:** One trustworthy handheld A/B investigation using built-in camera, audio, motion, touch and spoken guidance, with the agent service on the Mac over the local network. Hosted deployment is deferred.

**Deliverable:** A reproducible device build and local service, with run evidence for a complete guided investigation and explicitly recorded capability limits.

**Completion:** G-0001's outcome is Met with linked run evidence; required capability, concurrency, audio, interaction and recovery checks are resolved; in-scope ADRs are Accepted, Rejected or Withdrawn with rationale. Missing evidence or unresolved required failures prevents completion. Scope changes preserve the original result through dated revisions.

These are design-only iterations. No firmware or test runner has been built, and no hardware result is implied.

The user has agreed to start with C++/ESP-IDF, LVGL and a Python agent service. For iteration 4, run the service on the user's Mac over the local network, first with a scripted mock agent and then a live provider. The service endpoint is configurable for future hosting; deployment to the internet is outside this milestone.

### G-0001: A trustworthy live investigation

**Goal:** [G-0001](plans/G-0001-trustworthy-live-investigation.md) — Not started. The specs below are children of this goal; the order is a starting sequence, with dependencies stated separately.

| Order | Spec | Status | Depends on | Decision informed |
| --- | --- | --- | --- | --- |
| 1 | [Hardware baseline](plans/G-0001.01-hardware-baseline.md) | Not built | None | Actual panel/silicon/camera identity, peripheral ownership, reproducible versions |
| 2 | [Concurrent workload](plans/G-0001.02-concurrent-workload.md) | Not built | .01 | Rates, buffers, scheduling and memory budget |
| 3 | [Audio integrity](plans/G-0001.03-audio-integrity.md) | Not built | .01; repeat under .02 load | Raw measurement and speech-processing separation |
| 4 | [Agent interaction](plans/G-0001.04-agent-interaction.md) | Not built | .02, .03 | Protocol, latency, cancellation and WebSocket/WebRTC choice |
| 5 | [Power and recovery](plans/G-0001.05-power-recovery.md) | Not built | .01; repeat with .02/.04 | Power telemetry, wake behavior and recoverable evidence |

**Decisions:** [ADR-0001](adrs/ADR-0001-native-firmware-stack.md) covers the native stack; [ADR-0002](adrs/ADR-0002-local-instruments-connected-agent.md) covers local instruments and the connected agent. Each owns its acceptance conditions and review trigger. The [hardware-baseline spec](plans/G-0001.01-hardware-baseline.md#shared-run-evidence) owns the shared evidence format.

**Progress — 2026-09-20:** Planning only. Established M-0001 → G-0001 → five specs; no implementation evidence. Next action is the hardware baseline. Review ADR-0001 when that experiment records an outcome, including a partial or refuted result.

## Later hypotheses to write

A hosted agent-service experiment should test the same device protocol against an internet-accessible deployment without requiring the Mac. Define device authentication, encrypted transport, credential provisioning, capture retention and internet latency/recovery checks before implementation. Hosting and model providers remain open choices.

Choose later milestones and their goals from what M-0001 teaches, then write specs under those goals. Candidates include local ESP-DL inference, full-duplex speech/AEC tuning, wake words, higher-resolution video, USB peripherals, RS-485 fixtures, external environmental sensors, and additional radio protocols where board/firmware support is established. Each needs a bounded hypothesis and budget; none is a committed implementation feature.
