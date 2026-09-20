# Tricorder agent handoff

Updated: 2026-09-20

## Current state

G-0001 is **In progress**. Read [milestones](planning/milestones.md), [the goal](planning/plans/G-0001-trustworthy-live-investigation.md), and [.01 Observed](planning/plans/G-0001.01-hardware-baseline.md#observed) for authoritative progress. Preserve all original acceptance gates; .03 has verified isolated synthetic DSP only; .02/.04/.05 remain Not built.

- Connected Tab5: Espressif USB serial `E8:F6:0A:E2:E0:0E`, last ROM port `/dev/cu.usbmodem4`, P4 v1.3, 16 MB flash, 32 MB PSRAM, ST7121. Rediscover ports after reconnects; `/dev/cu.usbmodem1101` was a different endpoint.
- Two full original-flash reads match. Private backups, restore instructions, build/flash logs and run evidence: `.local/runs/20260920-baseline/`. Do not commit personal captures or flash contents.
- Both clean factory builds flashed and booted. Timestamp-derived binary differences are accounted for. The user explicitly approved testing both builds.
- Native `firmware/` reads sensor identities and RTC advancement, logs touch/raw IMU/power telemetry, and attempts a non-formatting SD roundtrip. No microSD is installed or available. User confirms the screen is stable; corner/center touches and tilt response are recorded.
- Keep the failed PPA alignment run. Full-frame PSRAM buffers fixed the observed abort; longer/concurrent validation remains open.
- [ADR-0003](planning/adrs/ADR-0003-tab5-diagnostic-foundation.md) is Active: pinned factory/IDF diagnostic foundation and single BSP ownership. Vendor helper return values/byte counts need scrutiny before measurement claims.

## Continue

`python3 tools/bootstrap.py` reproduces source pins/toolchain. `tools/idf.sh -C firmware build` builds the diagnostic. Host tests: `python3 -m unittest discover -s tests -v`. README documents serial collection. ESP-IDF configuration and USB writes required sandbox escalation in this environment.

Camera/PCM export: `media-boot-2` retains a readable 1280×720 frame and three seconds of four-slot raw audio with matching device/host hashes; 30 host tests pass. [ADR-0004](planning/adrs/ADR-0004-capture-completion.md) governs completion/partials.

Touch-triggered record/playback exists. The repeat in `acoustic-network-3` resolves the earlier slot discrepancy: user recognizes raw slots 0/2, hears none in 1/3, and still finds output quiet at 60%. Capture gain remains 24 dB; raw hashes are unchanged. Physical microphone mapping remains open. Volume slider and Wi-Fi symbol/error hints compile but are not flashed.

[ADR-0005](planning/adrs/ADR-0005-diagnostic-radio-startup.md) records deferred radio initialization and compatible task SRAM. Preserve failed `acoustic-network-1/2`; corrected `acoustic-network-3` completes twenty minutes with one boot and no event/capture errors. C6 reports 1.4.1; `lan-echo-1` passes three nonce/boot-matched exchanges. Host suite has 47 tests.

`headphones-1` confirms recognizable raw slots 0/2 in both headphone earpieces with better level than the speaker; slots 1/3 are static only. Its unexpected USB-reset attachment failure is preserved; independent strict actual-boot assessment passes with no capture errors. Credentials remain RAM-only.

The **Test 10 restarts** diagnostic exposed a real startup display race in `software-restarts-1`: LVGL refresh read objects while startup constructed them without the BSP lock. The corrected `software-restarts-2` passes ten consecutive ESP_RST_SW boots with all selected initialization checks; failed run and ELF are retained. Never count these as cold starts. No active collector remains from those runs.

Current device firmware includes startup FFT fixtures, volume slider and Wi-Fi hints. `device-spectrum-1` passes twelve P4 synthetic comparisons (four fixtures × three repeats), raw input hashes unchanged, maximum bin error 3.90e-7 FS, isolated computation 3.64–4.20 ms. Its collector handle 85881 is terminal; no serial capture is currently active. Build artifacts/ELF are archived at baseline `device-spectrum-build-1-artifacts/`; source hashes are in `device-spectrum-build-manifest.json`. Host suite: 56 passing tests. `.03` still needs speech separation, continuous acquisition, acoustic/load and SD verification.

Finish .01: physical microphone mapping and speaker level, ten cold starts, and SD checks when a card is available. Operator has been asked whether the rear battery is installed or power is USB-only, to plan cold-start/power fixtures. The official annotated photo https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/1132/C145_01.webp labels two front-bezel holes: MIC-L is closer to the USB/headset connector edge, MIC-R farther along the same bezel. This is documentation, not verified channel mapping. Local copy `/private/tmp/tricorder-tab5-front.webp` has been viewed.

Execute .02–.05 against their stated workloads/counts. Do not declare calibration from raw readings or synthetic arithmetic. Ask the user when physical interaction is needed; they are available to operate the device.

Maintain concise planning progress in the same commits as implementation. Observed entries are append-only. Record consequential decisions as they happen; reserved former ADR-0001/0002 were proposals, not revoked decisions. Inspect branch status before syncing and preserve local commits; do not reset to a remote baseline.

## User intent

Build the handheld Ask → measure → feedback → adjust → discover loop in [vision.md](vision.md), with Explore/Investigate/Compare and an inspectable capability view. Prioritize a person holding it, not unattended recording. The fan scenario uses camera, audio/FFT, A/B comparison, steadiness and spoken guidance; the IMU measures the instrument's movement unless physically coupled to an object.

The agreed experimental direction is C++/ESP-IDF, LVGL and a Python service on the Mac over LAN, mocked first then provider-backed. Provider and speech choices remain open. Preserve a configurable endpoint for later hosting, keep credentials service-side and measurement PCM separate from speech enhancement. Explain low-level ownership, memory and timing to an experienced programmer who is new to C++/embedded work. Physical tests, live-provider timing and operator ratings require real evidence.
