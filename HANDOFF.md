# Tricorder agent handoff

Updated: 2026-09-20

## Current state

G-0001 is **In progress**. Read [milestones](planning/milestones.md), [the goal](planning/plans/G-0001-trustworthy-live-investigation.md), and [.01 Observed](planning/plans/G-0001.01-hardware-baseline.md#observed) for authoritative progress. Preserve all original acceptance gates; later specs remain Not built.

- Connected Tab5: Espressif USB serial `E8:F6:0A:E2:E0:0E`, last ROM port `/dev/cu.usbmodem4`, P4 v1.3, 16 MB flash, 32 MB PSRAM, ST7121. Rediscover ports after reconnects; `/dev/cu.usbmodem1101` was a different endpoint.
- Two full original-flash reads match. Private backups, restore instructions, build/flash logs and run evidence: `.local/runs/20260920-baseline/`. Do not commit personal captures or flash contents.
- Both clean factory builds flashed and booted. Timestamp-derived binary differences are accounted for. The user explicitly approved testing both builds.
- Native `firmware/` reads sensor identities and RTC advancement, logs touch/raw IMU/power telemetry, and attempts a non-formatting SD roundtrip. No microSD is installed or available. User confirms the screen is stable; corner/center touches and tilt response are recorded.
- Keep the failed PPA alignment run. Full-frame PSRAM buffers fixed the observed abort; longer/concurrent validation remains open.
- [ADR-0003](planning/adrs/ADR-0003-tab5-diagnostic-foundation.md) is Active: pinned factory/IDF diagnostic foundation and single BSP ownership. Vendor helper return values/byte counts need scrutiny before measurement claims.

## Continue

`python3 tools/bootstrap.py` reproduces source pins/toolchain. `tools/idf.sh -C firmware build` builds the diagnostic. Host tests: `python3 -m unittest discover -s tests -v`. README documents serial collection. ESP-IDF configuration and USB writes required sandbox escalation in this environment.

Camera/PCM export: `media-boot-2` retains a readable 1280×720 frame and three seconds of four-slot raw audio with matching device/host hashes; 30 host tests pass. [ADR-0004](planning/adrs/ADR-0004-capture-completion.md) governs completion/partials.

Finish .01: physical microphone channels/record-playback, headphone checks, Wi-Fi roundtrip/C6 version, SD checks when a card is installed, ten cold starts and ten software resets. Then execute .02–.05 against their stated workloads and counts. Do not substitute USB resets for cold starts or declare calibration from raw readings. Ask the user when physical interaction is needed; they are available to operate the device.

Maintain concise planning progress in the same commits as implementation. Observed entries are append-only. Record consequential decisions as they happen; reserved former ADR-0001/0002 were proposals, not revoked decisions. Inspect branch status before syncing and preserve local commits; do not reset to a remote baseline.

## User intent

Build the handheld Ask → measure → feedback → adjust → discover loop in [vision.md](vision.md), with Explore/Investigate/Compare and an inspectable capability view. Prioritize a person holding it, not unattended recording. The fan scenario uses camera, audio/FFT, A/B comparison, steadiness and spoken guidance; the IMU measures the instrument's movement unless physically coupled to an object.

The agreed experimental direction is C++/ESP-IDF, LVGL and a Python service on the Mac over LAN, mocked first then provider-backed. Provider and speech choices remain open. Preserve a configurable endpoint for later hosting, keep credentials service-side and measurement PCM separate from speech enhancement. Explain low-level ownership, memory and timing to an experienced programmer who is new to C++/embedded work. Physical tests, live-provider timing and operator ratings require real evidence.
