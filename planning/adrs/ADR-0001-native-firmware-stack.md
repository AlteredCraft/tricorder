# 0001. Native firmware and interface stack

Status: Proposed
Date: 2026-09-20
Owner: Agent implementing G-0001.01–.03
Review trigger: First outcome recorded for G-0001.01; then each outcome or scope change in G-0001.02/.03, including partial/refuted results
Alignment: 2026-09-20 — user agreed to begin with this stack. Status remains Proposed pending the hardware and workload evidence below.

## Context

The [vision](../../vision.md) calls for realtime handheld investigations and learning the entire device. Camera, audio acquisition, signal processing, motion, touch, playback and network activity must share resources predictably. Support for the processor alone is insufficient evidence of support for the complete Tab5.

Research snapshot: 2026-09-20. Primary documentation/source was inspected; no build or device validation was performed. Exact dependency versions remain undecided.

## Options considered

| Option | Verified basis | Main benefit | Main cost or unresolved question |
| --- | --- | --- | --- |
| Native ESP-IDF with C/C++ | Factory demo uses ESP-IDF; official Tab5 BSP exists [1][2]. | Direct control over tasks, memory, multimedia APIs and accelerators. | Embedded concurrency, buffer lifetime and board integration are our responsibility. |
| Arduino with M5Unified/M5GFX | Official Tab5 guide documents setup and peripheral examples [3]. | Quick hardware experiments and convenient APIs. | Advanced pipelines still require native APIs; Arduino defaults may not fit our workload. |
| Arduino as an ESP-IDF component | Official supported integration [4]. | Access an Arduino-only library inside a native project. | Additional configuration and version coupling. |
| UIFlow2/MicroPython | Official Tab5 workflow exists [5]. | Interactive development and familiar language. | Complete concurrent camera/DSP/speech/UI behavior was not verified. This is an evidence gap, not a claim that it is impossible. |
| Rust | Current esp-hal lists P4 support [6]. | Memory-safety tools and low-level control. | Complete Tab5 multimedia integration was not verified; current manifest labels P4 support for silicon revision 3.x or later [7]. |

M5Unified supports ESP-IDF directly [8]. We do not need to adopt Arduino simply to reuse its hardware abstractions.

## Decision

**Propose** C++ application code on ESP-IDF/FreeRTOS, LVGL 9, and selected vendor drivers behind a small board interface. Use C libraries where they are the supported path. Keep the native build system and component dependency records reproducible. This proposal becomes an accepted decision only after the linked experiments supply evidence.

| Layer | Candidate | Intended use |
| --- | --- | --- |
| Scheduling | ESP-IDF FreeRTOS [9] | Independent acquisition, processing, UI and transport tasks with bounded queues. |
| Interface | LVGL 9 and compatible display/touch integration [10] | Explore/Investigate/Compare views, graphs and capability diagram. |
| Board integration | Espressif Tab5 BSP, M5Unified and factory-demo references [1][2][8] | Select one owner per peripheral and shared bus; do not independently initialize the same device from competing stacks. |
| Audio I/O | esp_codec_dev and I²S [2] | Capture and playback, with explicit channel mapping and buffer ownership. |
| Signal processing | ESP-DSP [11] | Local FFT, filtering and quantitative comparisons. |
| Video | esp_video and camera drivers [12] | Capture, preview and supported sensor controls. |
| Acceleration | PPA, JPEG/H.264 where useful [12][13] | Image transforms and encoding after profiling. |
| Speech | ESP-SR [14] | Optional voice activity detection, AEC, noise suppression and bounded commands. |
| Local inference | ESP-DL [15] | Later task-specific models within measured resource budgets. |
| Wireless | ESP-Hosted / esp_wifi_remote with compatible C6 firmware [16] | P4-to-C6 networking over the board's SDIO connection. |

The factory demo documents ESP-IDF 5.4.2 and pins LVGL 9.2.2 [1][17]. Those are reproduction references, not an assertion that they are the best final project versions. Reproduce a supported baseline on this unit, then deliberately update and pin the selected set. The demo's desktop build is useful for UI work but cannot validate device timing, memory bandwidth, power or peripherals.

## Consequences

We gain a direct route to native hardware features while learning scheduling, DMA/buffer ownership, memory placement and failure recovery. We take on C++ resource management, C-library integration, and driver compatibility work.

Specific assumptions to resolve:

- The supplied demo photo labels its LCD ST7121. Confirm the unit's label and active driver; M5Stack documents multiple panel revisions [18].
- BSP coverage is not complete: the published capability table marks battery support unavailable, despite the physical power-monitoring hardware [2]. Audit RTC, power telemetry, charging and wake separately.
- The BSP camera table and board description use different sensor names [2][18]. Identify the actual sensor and supported driver/mode instead of inferring it from a table.
- Native PPA or codec availability does not establish a frame-rate guarantee or prove that LVGL routes every drawing operation through hardware.
- The C6 firmware and host components are a compatibility set.
- Use speech processing without changing measurement audio; see [ADR-0002](ADR-0002-local-instruments-connected-agent.md).

Acceptance depends on [hardware baseline](../plans/G-0001.01-hardware-baseline.md), [combined load](../plans/G-0001.02-concurrent-workload.md), and [audio integrity](../plans/G-0001.03-audio-integrity.md). Revisit if required peripherals cannot coexist, panel support remains unreliable, or another route substantially reduces measured integration cost.

## Decision review

Acceptance conditions: The linked .01–.03 evidence must support the required native hardware integration, combined workload and raw-audio integrity. Resolve driver/version choices and record remaining limits before accepting. Optional ESP-DL, later acceleration and other deferred capabilities do not gate this decision; acceptance does not validate them.

- 2026-09-20: **Proposed.** Reviewed the user's agreement to start with this stack and the unbuilt .01–.03 specs. No hardware evidence exists, so technical acceptance remains unresolved. Next action: establish .01's reproducible hardware baseline, then review this ADR immediately against that result. Later gates remain .02/.03; do not wait until milestone closure to assess failures or revise the proposal.

## Primary research references

These links support the research snapshot. Moving branches and “latest” pages can change; archive the selected revisions in each build's manifest.

1. [M5Tab5 factory demo, including desktop and IDF builds](https://github.com/m5stack/M5Tab5-UserDemo)
2. [Published Tab5 BSP 1.3.0 capability table](https://components.espressif.com/components/espressif/m5stack_tab5/versions/1.3.0/readme)
3. [Tab5 Arduino guide and driver compatibility](https://docs.m5stack.com/en/arduino/m5tab5/program)
4. [Arduino as an ESP-IDF component](https://docs.espressif.com/projects/arduino-esp32/en/latest/esp-idf_component.html)
5. [Tab5 UIFlow2 guide](https://docs.m5stack.com/en/uiflow2/Tab5/program)
6. [esp-hal support statement](https://github.com/esp-rs/esp-hal)
7. [esp-hal manifest and P4 silicon-revision note](https://github.com/esp-rs/esp-hal/blob/main/esp-hal/Cargo.toml)
8. [M5Unified supported frameworks and devices](https://github.com/m5stack/M5Unified)
9. [ESP-IDF FreeRTOS](https://docs.espressif.com/projects/esp-idf/en/stable/esp32p4/api-reference/system/freertos.html)
10. [ESP LVGL port 2.9.0](https://components.espressif.com/components/espressif/esp_lvgl_port/versions/2.9.0/readme)
11. [ESP-DSP 1.8.2, including P4-optimized routines](https://components.espressif.com/components/espressif/esp-dsp/versions/1.8.2/readme)
12. [esp_video 2.5.0 support matrix](https://components.espressif.com/components/espressif/esp_video/versions/2.5.0/readme)
13. [P4 Pixel-Processing Accelerator](https://docs.espressif.com/projects/esp-idf/en/stable/esp32p4/api-reference/peripherals/ppa.html)
14. [ESP-SR](https://github.com/espressif/esp-sr)
15. [ESP-DL](https://github.com/espressif/esp-dl)
16. [Factory-demo hosted-network dependencies](https://github.com/m5stack/M5Tab5-UserDemo/blob/main/platforms/tab5/main/idf_component.yml)
17. [Factory-demo library versions](https://github.com/m5stack/M5Tab5-UserDemo/blob/main/repos.json)
18. [Tab5 hardware, pin map and revisions](https://docs.m5stack.com/en/core/Tab5)
