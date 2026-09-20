# Stack recommendation and validation plan

Date: 2026-09-20
Status: Proposed; hardware experiments not built

## Start here

The recommendation is **C++ on ESP-IDF/FreeRTOS, LVGL 9, selected M5Stack/Espressif drivers, ESP-DSP, and a Python agent service**. Introduce ESP-SR and ESP-DL after measuring the basic workload. Start transport evaluation with WebSockets; compare WebRTC if continuous, interruptible speech warrants it.

This captures the research and proposals discussed for [Tricorder](../vision.md). Documentation and source inspection establish candidate support, not successful operation on this unit. No firmware, dependencies, version lock, or hardware measurements have been added.

## Planning map

Following the planning templates, goals describe outcomes, specs test hypotheses, and ADRs capture trade-offs. The numbered goal and specs live together in `planning/plans/`, using the `plans/G-NNNN...` filename convention in the guidelines. Existing templates and guidelines remain intact.

- [G-0001: A trustworthy live investigation](plans/G-0001-trustworthy-live-investigation.md)
- [ADR-0001: Native firmware and interface stack](adrs/ADR-0001-native-firmware-stack.md) — Proposed
- [ADR-0002: Local instruments and connected agent](adrs/ADR-0002-local-instruments-connected-agent.md) — Proposed

| Order | Experiment | Key question | Depends on |
| --- | --- | --- | --- |
| 1 | [G-0001.01 Hardware baseline](plans/G-0001.01-hardware-baseline.md) | Can we reproduce and control the actual board's capabilities? | None |
| 2 | [G-0001.02 Concurrent workload](plans/G-0001.02-concurrent-workload.md) | Can measurements, preview, touch, and networking coexist responsively? | .01 |
| 3 | [G-0001.03 Audio integrity](plans/G-0001.03-audio-integrity.md) | Can measurement audio remain trustworthy while speech is processed? | .01; repeat under .02 load |
| 4 | [G-0001.04 Agent interaction](plans/G-0001.04-agent-interaction.md) | Can the agent guide a live investigation without blocking instruments? | .02, .03 |
| 5 | [G-0001.05 Power and recovery](plans/G-0001.05-power-recovery.md) | Can a handheld session recover predictably and expose its energy cost? | .01; repeat with .02/.04 |

All five are **Not built**. See the [phase 1 roadmap](../docs/roadmap.md). Proposed numeric targets below are project acceptance targets, not manufacturer guarantees or observed results. Change them only in a dated proposal revision before running the affected experiment; preserve failures at the original settings.

## Evidence contract for the experiments

Each experiment should produce a private/local run folder, not committed personal captures:

- `manifest.json`: run/spec ID; UTC date and monotonic clock definition; board, silicon, display, camera and C6 firmware identity; firmware commit; toolchain/component versions and lock hashes; configuration; fixture/setup; expected workload; calibration status.
- `events.jsonl`: run/session/boot IDs, event name, device monotonic timestamp, host receipt timestamp when applicable, sequence number, capture ID and relevant fields.
- `metrics.csv`: timestamped workload, frame/capture counts, rates, latency, queue depth, overruns, allocation failures, free internal RAM/PSRAM, largest free blocks, task stack high-water marks, reset reason and power readings.
- `captures/`: test PCM/WAV, images and checksums with rate, gain, format, channels, processing flags, and sample/frame counters.
- `summary.json`: each acceptance check, sample count, p50/p95/max where appropriate, missing-data count, pass/fail/inconclusive, and paths to source records.
- `operator-notes.md`: dated observations, fixture movements and usability ratings, explicitly distinguished from instrument measurements.

These are proposed record formats to implement in the spikes. They do not yet exist. Every build step gets its check before implementation; append results under that spec's Observed section. Missing evidence is inconclusive, not a pass.

Use device monotonic time for local durations; never subtract unsynchronized host and device timestamps. Record boot boundaries. Use round-trip timing or a measured clock-offset estimate for cross-device analysis, including uncertainty. A display flush callback measures software completion, not necessarily photon-visible response.

Keep sampling and calibration settings comparable for A/B runs. Change one independent variable at a time before combining loads. Retain at least three repeated runs for a claimed performance result. Do not use appearance of the UI as proof of correctness; record physical observations and timing in run artifacts.

## Decision gates

1. Establish the board baseline and reproducible build before accepting exact driver/version choices.
2. Prove combined workload and raw audio integrity before committing to the interaction architecture.
3. Measure conversational latency and interruption before deciding WebSocket versus WebRTC.
4. Record runtime, wake behavior and failure recovery before setting product battery-life claims.
5. Accept or revise the Proposed ADRs using linked run evidence. A failed capability can reduce scope or motivate a replacement component; it must not disappear from the record.

Future local models, external sensors, speech wake words and high-resolution video need their own bounded experiments after these gates.
