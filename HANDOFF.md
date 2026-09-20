# Tricorder agent handoff

Updated: 2026-09-20

## Current state

G-0001 is **In progress**. Read [milestones](planning/milestones.md), [the goal](planning/plans/G-0001-trustworthy-live-investigation.md), and [.01 Observed](planning/plans/G-0001.01-hardware-baseline.md#observed) for authoritative progress. Preserve all original acceptance gates. .03 has verified synthetic DSP and isolated live raw/speech separation; .02 has verified isolated camera/audio/motion baselines. .04/.05 remain Not built.

- Connected Tab5: Espressif USB serial `E8:F6:0A:E2:E0:0E`, last ROM port `/dev/cu.usbmodem4`, P4 v1.3, 16 MB flash, 32 MB PSRAM, ST7121. Rediscover ports after reconnects; `/dev/cu.usbmodem1101` was a different endpoint.
- Two full original-flash reads match. Private backups, restore instructions, build/flash logs and run evidence: `.local/runs/20260920-baseline/`. Do not commit personal captures or flash contents.
- Both clean factory builds flashed and booted. Timestamp-derived binary differences are accounted for. The user explicitly approved testing both builds.
- Native `firmware/` reads sensor identities and RTC advancement, logs touch/raw IMU/power telemetry, and attempts a non-formatting SD roundtrip. No microSD is installed or available. User confirms the screen is stable; corner/center touches and tilt response are recorded.
- Keep the failed PPA alignment run. Full-frame PSRAM buffers fixed the observed abort; longer/concurrent validation remains open.
- [ADR-0003](planning/adrs/ADR-0003-tab5-diagnostic-foundation.md) is Active: pinned factory/IDF diagnostic foundation and single BSP ownership. Vendor helper return values/byte counts need scrutiny before measurement claims.

## Continue

`python3 tools/bootstrap.py` reproduces source pins/toolchain. `tools/idf.sh -C firmware build` builds the diagnostic. Host tests: `python3 -m unittest discover -s tests -v`. README documents serial collection. ESP-IDF configuration and USB writes required sandbox escalation in this environment.

Camera/PCM export: `media-boot-2` retains a readable 1280×720 frame and three seconds of four-slot raw audio with matching device/host hashes; 30 host tests pass. [ADR-0004](planning/adrs/ADR-0004-capture-completion.md) governs completion/partials.

Touch-triggered record/playback exists. The repeat in `acoustic-network-3` resolves the earlier slot discrepancy: user recognizes raw slots 0/2, hears none in 1/3, and still finds output quiet at 60%. Capture gain remains 24 dB; raw hashes are unchanged. The later six-take fixture below supersedes the unresolved relative physical association. Volume slider and Wi-Fi symbol/error hints are flashed.

[ADR-0005](planning/adrs/ADR-0005-diagnostic-radio-startup.md) records deferred radio initialization and compatible task SRAM. Preserve failed `acoustic-network-1/2`; corrected `acoustic-network-3` completes twenty minutes with one boot and no event/capture errors. C6 reports 1.4.1; `lan-echo-1` passes three nonce/boot-matched exchanges. Host suite has 47 tests.

`headphones-1` confirms recognizable raw slots 0/2 in both headphone earpieces with better level than the speaker; slots 1/3 are static only. Its unexpected USB-reset attachment failure is preserved; independent strict actual-boot assessment passes with no capture errors. Credentials remain RAM-only.

The **Test 10 restarts** diagnostic exposed a real startup display race in `software-restarts-1`: LVGL refresh read objects while startup constructed them without the BSP lock. The corrected `software-restarts-2` passes ten consecutive ESP_RST_SW boots with all selected initialization checks; failed run and ELF are retained. Never count these as cold starts. No active collector remains from those runs.

Current firmware automatically runs a 60-second camera baseline, three live raw/speech captures, synthetic FFT/speech fixtures, a 60-second audio baseline and a 60-second 100 Hz motion baseline. Manual record/restart/audio buttons remain available. **84 host tests and the P4 build pass.** Current artifacts: `.local/runs/20260920-baseline/imu-baseline-build-2-artifacts/`; hashes in `imu-baseline-build-manifest.json` and run `firmware.json`. Source hashes identify the dirty version precisely.

**No active collector.** Latest session37784 is terminal: `imu-baseline-1`, boot `9662108e1f9d1737bffec6230c66b60e`, firmware `1125cdd-dirty`. Final run summary, three isolated baseline assessments, live audio, ingress, synthetic speech and FFT all pass. Camera image is hash-verified and visually readable. Tests/build/flash are also terminal. The diagnostic is idle; current Wi-Fi credentials were cleared by reset and no network is associated.

Earlier sessions72562 (`camera-baseline-1`, boot `b028ac611d1a491e66a034fbc13ef2ad`) and66290 (`live-audio-1`, boot `f75247b219badd835d328177a1638f1c`) are terminal. Preserve original camera-run summary: a host required-check typo (`ina226226_manufacturer`) made it inconclusive. Independent `corrected-check-summary.json` passes corrected selection and carries capture/integrity errors forward. Do not rewrite original summary/manifest. Camera `-resource-assessment.json` adds strict CPU/stack/SRAM verification to its original assessment.

**Verified isolated results:** two 1,800-frame native 1280×720 RGB565 camera runs at ~30 fps; three 6,000-block / 60-second audio baselines; one 6,000-poll motion run at 100 Hz. No observed camera starvation, raw-audio loss/mutation, or IMU read/freshness/deadline failures in these runs. Driver rejects 640×480. Checked motion reuses the BSP-owned Bosch device via `bmi270_init` wrapping, propagates init/config/enable/read failures, verifies 200 Hz hardware ODR and ±4g/±1000dps readback, and samples latest registers at 100 Hz. Intermediate hardware samples are deliberately not retained. Tests inject failures and missing/corrupt timing/resource evidence. These are sequential baselines, not calibration or combined-load evidence.

**Next independent work:** implement/test the 30 fps animated-UI baseline, then JPEG and combined staging. Source notes are in baseline `imu-ui-followup-notes.md`. LVGL has refresh period33ms; `LV_EVENT_FLUSH_START/FINISH` bracket the flush callback, not physical presentation. The vendor callback does blocking PPA rotation before panel draw; DSI partial-mode completion invokes `lv_disp_flush_ready`. Preserve BSP locks and callbacks. Record actual panel submissions for input-to-submit claims and distinct animation/frame IDs; timer callbacks alone do not prove display rate. Then prepare bounded streaming/host backpressure and Mac mock-agent work. Keep tests first, actual ownership explicit and every failed run retained.

The user is **away** and asks us to make autonomous G1 progress. No physical input is pending. Maintain [TODO.md](TODO.md) for operator follow-ups. Wi-Fi credentials are RAM-only and SD remains absent. Do not count isolated baselines as combined runs, automatic inputs as physical input trials, software resets as cold starts, or mock timings as live-provider results.

**Microphone fixture complete:** `audio-ingress-1` collector session88533 is terminal. User confirms all six individual takes (visible IDs2–6; ID1 joined by request timing). Three near-connector takes favor rawslot2; three farther-opening takes favor rawslot0. Ratios0/2 are -2.76/-1.81/-1.74dB near, +2.24/+0.70/+1.32dB far. `microphone-position.json` records the supported relative association, cross-pickup and modest margins. User hears 0 best,2good,1/3no phrase. Final serial/capture and seven ingress epochs pass. Keep physical position names; this association differs from factory MIC-L/R comments combined with the annotated photo. Earlier `speech-replay-1` count discrepancy remains retained.

`audio-ingress-1/speech-replay.json` also passes24synthetic pairs; earlier `speech-replay-1` and `device-spectrum-1` remain retained. No current SD evidence or calibration claim.

Finish .01: retain the fixture-limited microphone association, resolve speaker level/remaining capability limits, ten cold starts, and SD checks when a card is available. Operator confirms the rear battery is installed; no microSD is available. The official annotated photo https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/1132/C145_01.webp labels MIC-L near the USB/headset connector edge and MIC-R farther along the same front bezel; these are documentation labels, not verified raw-slot assignments. Software and USB resets are not cold starts.

Execute .02–.05 against their stated workloads/counts. Do not declare calibration from raw readings or synthetic arithmetic. The user is away; put physical interaction follow-ups in TODO.md and continue independent work.

Maintain concise planning progress in the same commits as implementation. Observed entries are append-only. Record consequential decisions as they happen; reserved former ADR-0001/0002 were proposals, not revoked decisions. Inspect branch status before syncing and preserve local commits; do not reset to a remote baseline.

## User intent

Build the handheld Ask → measure → feedback → adjust → discover loop in [vision.md](vision.md), with Explore/Investigate/Compare and an inspectable capability view. Prioritize a person holding it, not unattended recording. The fan scenario uses camera, audio/FFT, A/B comparison, steadiness and spoken guidance; the IMU measures the instrument's movement unless physically coupled to an object.

The agreed experimental direction is C++/ESP-IDF, LVGL and a Python service on the Mac over LAN, mocked first then provider-backed. Provider and speech choices remain open. Preserve a configurable endpoint for later hosting, keep credentials service-side and measurement PCM separate from speech enhancement. Explain low-level ownership, memory and timing to an experienced programmer who is new to C++/embedded work. Physical tests, live-provider timing and operator ratings require real evidence.
