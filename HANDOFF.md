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

Touch-triggered record/playback exists. The repeat in `acoustic-network-3` resolves the earlier slot discrepancy: user recognizes raw slots 0/2, hears none in 1/3, and still finds output quiet at 60%. Capture gain remains 24 dB; raw hashes are unchanged. Physical microphone mapping remains open. Volume slider and Wi-Fi symbol/error hints are flashed.

[ADR-0005](planning/adrs/ADR-0005-diagnostic-radio-startup.md) records deferred radio initialization and compatible task SRAM. Preserve failed `acoustic-network-1/2`; corrected `acoustic-network-3` completes twenty minutes with one boot and no event/capture errors. C6 reports 1.4.1; `lan-echo-1` passes three nonce/boot-matched exchanges. Host suite has 47 tests.

`headphones-1` confirms recognizable raw slots 0/2 in both headphone earpieces with better level than the speaker; slots 1/3 are static only. Its unexpected USB-reset attachment failure is preserved; independent strict actual-boot assessment passes with no capture errors. Credentials remain RAM-only.

The **Test 10 restarts** diagnostic exposed a real startup display race in `software-restarts-1`: LVGL refresh read objects while startup constructed them without the BSP lock. The corrected `software-restarts-2` passes ten consecutive ESP_RST_SW boots with all selected initialization checks; failed run and ELF are retained. Never count these as cold starts. No active collector remains from those runs.

Current device firmware includes startup FFT/speech fixtures, visible `TAKE audio-N` labels, button/stage events and IDF RX byte/loss accounting. Archived `speech-replay-1` passes 24 synthetic raw/speech comparisons: input unchanged, enabled output within one PCM count, isolated compute 1.365–1.395 ms/2048 frames. `device-spectrum-1` passes twelve FFT comparisons (maximum bin error 3.90e-7 FS). Neither establishes live pipeline or load acceptance. Host suite: 65 passing tests.

**Active collector:** session 88533, run `.local/runs/20260920-baseline/audio-ingress-1`, 1800-second bound, graceful stop file `audio-ingress-1/STOP`. Verify the handle before acting. Boot `82aeac05b8467adaf8898ff97dfccff6`; startup `audio-0` and operator `audio-1` show exact 1,152,000-byte reads and zero in-epoch driver loss/errors. This is a live snapshot, not final assessment. Build artifacts are `audio-ingress-build-3-artifacts/`, hashes `audio-ingress-build-manifest.json` and run `firmware.json`. After stopping, run `python3 -m tools.audio_ingress_evidence RUN` and the existing synthetic comparison tools; retain any failure.

**Pending operator question:** first farther-opening recording, expected `TAKE audio-4`; near-connector opening lightly covered, same phrase, 2–3 cm distance and volume. Verify each take before requesting the next two. Three near-connector takes audio-1/2/3 are complete; operator explicitly saw IDs 2/3 (missed 1). User reports slot 0 best quality, 2 good, 1/3 no phrase. All driver epochs pass. Near-position slot-0/2 RMS ratios are -2.76, -1.81 and -1.74 dB; means are near zero. No physical mapping conclusion yet. Earlier `speech-replay-1` reported three takes per position but logged only two operator captures: preserve that mismatch.

**Unflashed candidate:** live block hashing and separate synchronous speech output now compile. 68 host tests pass, including independent live raw/derived provenance/timing checks. Artifacts `.local/runs/20260920-baseline/live-audio-build-2-artifacts/`, hashes `live-audio-build-manifest.json`. Keep the current device firmware unchanged through the microphone fixture. After completing/stopping that collector, flash the archived candidate and gather three actual captures; assess with `python3 -m tools.live_audio_evidence RUN`. No live-separation hardware pass yet. Source hashes establish the binary even if Git has advanced.

Finish .01: physical microphone mapping and speaker level, ten cold starts, and SD checks when a card is available. Operator confirms the rear battery is installed; no microSD is available. The official annotated photo https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/1132/C145_01.webp labels MIC-L near the USB/headset connector edge and MIC-R farther along the same front bezel; these are documentation labels, not verified raw-slot assignments. Software and USB resets are not cold starts.

Execute .02–.05 against their stated workloads/counts. Do not declare calibration from raw readings or synthetic arithmetic. Ask the user when physical interaction is needed; they are available to operate the device.

Maintain concise planning progress in the same commits as implementation. Observed entries are append-only. Record consequential decisions as they happen; reserved former ADR-0001/0002 were proposals, not revoked decisions. Inspect branch status before syncing and preserve local commits; do not reset to a remote baseline.

## User intent

Build the handheld Ask → measure → feedback → adjust → discover loop in [vision.md](vision.md), with Explore/Investigate/Compare and an inspectable capability view. Prioritize a person holding it, not unattended recording. The fan scenario uses camera, audio/FFT, A/B comparison, steadiness and spoken guidance; the IMU measures the instrument's movement unless physically coupled to an object.

The agreed experimental direction is C++/ESP-IDF, LVGL and a Python service on the Mac over LAN, mocked first then provider-backed. Provider and speech choices remain open. Preserve a configurable endpoint for later hosting, keep credentials service-side and measurement PCM separate from speech enhancement. Explain low-level ownership, memory and timing to an experienced programmer who is new to C++/embedded work. Physical tests, live-provider timing and operator ratings require real evidence.
