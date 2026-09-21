## G-0001. A trustworthy live investigation

**Milestone.** [M-0001: Validate the handheld investigation](../milestones.md#m-0001-validate-the-handheld-investigation).

**Outcome.** A person holding the Tricorder can ask a question, collect and compare evidence, and receive guidance while the instrument remains responsive and clearly represents what it has measured.

**Driver.** The [vision](../../vision.md): realtime collaboration, tactile use, learning every built-in sensor, and explanations grounded in evidence.

**Measure.** Repeated run records establish the available hardware capabilities, observation integrity, response timing, interruption/recovery behavior and energy cost of a complete guided A/B investigation. Each supported capability has recorded evidence; unavailable or deferred capabilities are explicit. Numeric acceptance targets are proposed in the serving specs.

**Specs.**

- [G-0001.01 Hardware baseline](G-0001.01-hardware-baseline.md)
- [G-0001.02 Concurrent workload](G-0001.02-concurrent-workload.md)
- [G-0001.03 Audio integrity](G-0001.03-audio-integrity.md)
- [G-0001.04 Agent interaction](G-0001.04-agent-interaction.md)
- [G-0001.05 Power and recovery](G-0001.05-power-recovery.md)

**Status.** In progress; resumed 2026-09-21. Hardware baseline and isolated live-audio integrity evidence are recorded; the full investigation and remaining acceptance gates are unverified.

**Progress.** 2026-09-20: Planning only; parent milestone recorded. Next action is G-0001.01's hardware baseline. No outcome evidence exists yet.

**Progress.** 2026-09-20: Started [.01](G-0001.01-hardware-baseline.md#observed): serial access, recovery checks and pinned factory/toolchain setup. Remaining specs are Not built.

**Progress.** 2026-09-20: Factory reproduction and native identity/RTC checks recorded in [.01](G-0001.01-hardware-baseline.md#observed); diagnostic foundation adopted in [ADR-0003](../adrs/ADR-0003-tab5-diagnostic-foundation.md). No SD card; full hardware and guided-investigation gates remain open.

**Progress.** 2026-09-20: [.01](G-0001.01-hardware-baseline.md#observed) now retains a readable camera frame and hash-verified raw PCM. Acoustic/network/restart checks and SD-dependent gates remain open; [ADR-0004](../adrs/ADR-0004-capture-completion.md) records capture completion.

**Progress — interactive diagnostics.** 2026-09-20: Audible but faint playback recorded; physical slot mapping remains unresolved. Radio startup corrected and Wi-Fi setup prepared; LAN evidence, storage and restart gates remain open. See [.01](G-0001.01-hardware-baseline.md#observed) and [ADR-0005](../adrs/ADR-0005-diagnostic-radio-startup.md).

**Progress — host preparation.** 2026-09-20: [.03](G-0001.03-audio-integrity.md#observed) starts deterministic desktop DSP fixtures while .01 operator checks wait. Hardware dependencies and all acceptance thresholds remain unchanged.

**Progress — LAN verified.** 2026-09-20: [.01](G-0001.01-hardware-baseline.md#observed) records three matched LAN round trips and recognizable raw-slot 0/2 playback. Headphone/physical mapping, storage and restart gates remain open.

**Progress — headphones and software resets.** 2026-09-20: [.01](G-0001.01-hardware-baseline.md#observed) confirms both-ear headphone playback and ten software-reset boots after correcting a display race. Cold starts, microphone mapping, storage and later acceptance gates remain open.

**Progress — device DSP.** 2026-09-20: [.03](G-0001.03-audio-integrity.md#observed) passes three repetitions of all four synthetic FFT fixtures on P4. Speech separation, continuous acquisition, acoustic/load and SD checks remain open.

**Progress — speech replay.** 2026-09-20: [.03](G-0001.03-audio-integrity.md#observed) verifies synthetic raw/speech separation on P4. Live ingress checks are prepared; microphone mapping remains ambiguous and all remaining gates stay open.

**Progress — tracked microphone trials.** 2026-09-20: [.01](G-0001.01-hardware-baseline.md#observed) records repeated physical-position response and [.03](G-0001.03-audio-integrity.md#observed) finalizes seven clean isolated ingress epochs. [.02](G-0001.02-concurrent-workload.md#observed) begins sustained-audio preparation; full combined, cold-start, storage and interaction gates remain open.

**Progress — live audio boundary.** 2026-09-20: [.03](G-0001.03-audio-integrity.md#observed) verifies three live raw/speech pairs and records [ADR-0006](../adrs/ADR-0006-raw-audio-and-derived-speech.md). Sustained/combined workloads and the full guided investigation remain unverified.

**Progress — isolated baselines.** 2026-09-20: [.02](G-0001.02-concurrent-workload.md#observed) verifies native camera acquisition at 30 fps and two sustained audio runs. Remaining isolated/combined stages and the full investigation stay open. User follow-ups are in [TODO.md](../../TODO.md).

**Progress — checked motion baseline.** 2026-09-20: [.02](G-0001.02-concurrent-workload.md#observed) passes 6,000 checked IMU polls at 100 Hz and repeats camera/audio integrity checks. Vendor error propagation is corrected; full concurrent and guided-investigation acceptance remains open.

**Progress — animated display.** 2026-09-20: [.02](G-0001.02-concurrent-workload.md#observed) passes an isolated 30.30 fps display-submission baseline after correcting timer drift and retaining a failed capture affected by host sleep. Camera/audio/motion regressions pass; JPEG/network, combined loads and the guided investigation remain open.

**Progress — stopping checkpoint.** 2026-09-20: Camera+JPEG candidate builds and decodes 30 images but fails camera completion accounting; later sustained regressions are skipped. 98 host tests pass. Collection is stopped and failed evidence retained. Resume with the [.02 regression](G-0001.02-concurrent-workload.md#observed), using [HANDOFF.md](../../HANDOFF.md); user/equipment follow-ups remain in [TODO.md](../../TODO.md). Full G-0001 acceptance remains open.

**Progress — camera/JPEG regression resolved.** 2026-09-21: [.02](G-0001.02-concurrent-workload.md#observed) passes 1,800 ordered camera frames and 30 independently decoded JPEGs, plus all sequential audio/IMU/UI and live/synthetic regressions. Source hashing/copying needs a bounded four-buffer ring and FIFO completion delivery, recorded in [ADR-0007](../adrs/ADR-0007-bounded-camera-fifo.md). 103 host tests and P4 compilation pass; failed runs remain retained. JPEG queued-timeout ownership is the next engineering task before preview/concurrency. Full G-0001 and operator/storage gates remain open.

**Progress — JPEG error-path protection verified.** 2026-09-21: [.02](G-0001.02-concurrent-workload.md#observed) reproduces a real queued-JPEG timeout and verifies fail-stop before unsafe driver unwinding. The user-approved expected-panic test is retained separately from normal acceptance. Normal firmware is restored and passes all sequential/live/synthetic regressions;112 host tests pass. [ADR-0008](../adrs/ADR-0008-jpeg-error-path-fail-stop.md) records the bounded policy. Preview/concurrency, device memory-return and all original full-investigation gates remain open.

**Progress — live preview verified.** 2026-09-21: [.02](G-0001.02-concurrent-workload.md#observed) preserves1,800 native frames while displaying an owned, explicitly lossy half-rate preview and encoding30 JPEGs. Core1 rendering and explicit timer wake resolve retained camera-loss/startup failures. All sequential/live/synthetic regressions and121 host tests pass. [ADR-0009](../adrs/ADR-0009-owned-preview-and-render-placement.md) records the bounded choice. Full simultaneous workloads, host backpressure, device memory return and all original investigation/operator gates remain open.
