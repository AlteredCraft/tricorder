# Tricorder agent handoff

Updated: 2026-09-21, camera/JPEG regression verified

G-0001 is **In progress**. Authoritative gates and concise outcomes are in [milestones](planning/milestones.md) and [G-0001](planning/plans/G-0001-trustworthy-live-investigation.md). .01 hardware, .02 isolated workloads and .03 audio integrity have evidence; full acceptance is unverified. .04/.05 remain Not built. Preserve original thresholds, counts and failed runs. Observed sections are append-only; details belong in commits/private evidence.

**Work resumed at the user’s request.** G-0001 remains active and incomplete. No collector, build, flash or keep-awake process remains active. Next: JPEG queued-timeout ownership and allocation/shutdown fault tests, then preview/concurrency. User/equipment follow-ups are in [TODO.md](TODO.md); no physical input is pending now.

## Device and execution

- Correct Tab5: USB serial `E8:F6:0A:E2:E0:0E`, verified 2026-09-21 at `/dev/cu.usbmodem1101`, P4 v1.3, 16 MB flash, 32 MB PSRAM, ST7121. Rediscover and check **serial identity**, not just the path: the earlier port assignments are stale. `.tools/python-env/bin/python -m serial.tools.list_ports -v` reports identity.
- Battery pack installed. No microSD installed or available. Wi-Fi credentials are RAM-only and the current boot is not associated; the user previously completed three matched LAN exchanges over 2.4 GHz.
- Verified original flash backup (two matching full reads), restore instructions, artifacts and private captures are in `.local/runs/20260920-baseline/`. Do not commit captures, backup contents or secrets. Both factory builds were explicitly approved and booted.
- Bootstrap: `python3 tools/bootstrap.py`; build: `tools/idf.sh -C firmware build`; tests: `python3 -m unittest discover -s tests -q`. Toolchain/USB/git writes required sandbox escalation here. No push requested.
- **Prevent host sleep during serial runs:** prefix the collector with `/usr/bin/caffeinate -is`; its assertions automatically end with the collector. A sleeping Mac lost whole USB export intervals while the battery-powered Tab5 kept running. Do not infer successful device continuity from a missing host interval.
- Current diagnostic attempts a 60-second camera+JPEG stage, then sequential audio/motion/display baselines plus short live and synthetic audio fixtures; allow eight minutes for a successful full run. A failed camera check skips the later sustained stages. Manual record/restart/audio controls remain available. Reopening USB can reset the board. Never restart a process merely because an observation timeout expires; inspect its exact handle/state first.

## Current checkpoint: camera/JPEG and sequential regressions pass

**103 host tests and the P4 build pass.** Current flashed firmware is `8c98c00-dirty`, with exact sources, binary/ELF/map and hashes archived in `.local/runs/20260921-camera/jpeg-fifo-1-artifacts/` and `jpeg-fifo-1-manifest.json`. Archive and current source/build hashes match. Later host-assessor changes did not alter firmware.

`jpeg-fifo-1`, boot `0abb801259aea44bed22ee77eef014b3`, collector session **85731 is terminal**, stopped cleanly via STOP. Final serial summary, all four sustained baselines, JPEG, live-audio/ingress, synthetic speech and FFT pass independently. No serial gaps, capture errors or incomplete captures; all 30 JPEGs decode with matching independent source/copy/post-encode hashes and final raw witness. Final JPEG is visually readable. FFT must use `.local/runs/20260920-audio-reference-2`, whose impulse peak is correctly non-unique.

Camera: 1,800 consecutive rows at 29.999 fps over 60.001 s, zero reuse/order errors or unaccounted completions; frame p95/max 33.335/33.366 ms. JPEG source hash/copy p95 35.208/34.121 ms; worker p95/max 91.972/92.298 ms. Maximum camera-buffer hold remains 69.405 ms; four bounded buffers absorb this burst. PSRAM free/largest minima 7,289,732/7,208,960 bytes; JPEG stack margin 6,368 bytes. UI: 1,819 states at 30.302 software submissions/s, p95/max 47.216/49.960 ms. Audio: 6,000 blocks; IMU: 6,000 polls at 100 Hz. These are isolated/sequential results, not combined-load or physical-input acceptance.

Mechanism: backup is disabled in the pinned CSI configuration. When the queued list empties, the shim supplies the active DMA buffer again and suppresses delivery; the old observer still counted its completion. It also pushes done buffers onto a newest-first list. `camera_receive.cpp` removes the oldest done element under the original stream lock, taking the existing counting semaphore and preserving free flags; it delegates other video devices to the original path. Private header dependency and linker inclusion are explicit. `camera_ingress` counts active-buffer reuse. Stop-tail counts use a separate pre-STREAMOFF snapshot; the final JPEG hash/copy occurs after stopping. [ADR-0007](planning/adrs/ADR-0007-bounded-camera-fifo.md) records this bounded choice.

Preserved intermediate failure: `jpeg-ring-1`, boot `0e95de451d730b06f0ad45e1e2c83aa9`, session **54169 terminal**. Four buffers retain all 1,800 frames but reverse queued delivery order; its device summary passes while independent camera and dependent JPEG assessments FAIL. All 30 JPEGs decode. Audio/IMU/UI and live/synthetic speech pass. Its initial `device-spectrum.json` used obsolete reference-1 and fails on the impulse peak; `device-spectrum-corrected.json` separately passes reference-2. Preserve both. Exact ring artifacts/manifests are alongside the FIFO candidate.

**Next ownership issue:** `.local/runs/20260921-camera/jpeg-lifecycle-review.md` records a pinned-driver queued-timeout risk. `jpeg_encoder_process` ignores the result of `dma2d_force_end`; a queued job without an RX channel may not be cancelled, yet our worker currently releases its input slot after the error. Reproduce this path and establish quiescence or fail closed before adding PPA/preview contention. Normal successful runs do not prove error-path safety. Allocation saturation, cleanup and mode-cycle memory return are also open.

## Earlier failing JPEG checkpoint (retained)

`jpeg-baseline-1`, boot `efc223ac6c12b69d6a23e3460267c6dd`, session **33205 terminal**, remains FAIL. It delivered 1743 rows versus 1802 callbacks: 57 skipped sequence IDs across 32 gaps plus two completions after the final delivered frame. Its arithmetic `discarded_completed_at_stop=59` is not proof of stop-time discards. All 30 JPEGs decode and match hashes, but later sustained stages were skipped. This is not a preview-drop waiver.

Original firmware/artifacts remain under `.local/runs/20260920-baseline/jpeg-build-2-artifacts/` and `jpeg-build-manifest.json`, binary SHA-256 `6e5ed511639aa0762835b582ded6158d6d07412a36251e4cb8b27ee2c9cb8e8b`. Original capture/assessment and 98-test log are unchanged. The device now runs the FIFO candidate above.

## Previous passing build (fallback reference)

**92 host tests and P4 build passed at this earlier checkpoint (`557ddb1`).** Previous source/artifact manifest: baseline `ui-baseline-build-2-manifest.json`; archived binary/ELF/map and exact source snapshot: `ui-baseline-build-2-artifacts/`. Source hashes are authoritative despite the dirty version string.

**No active collector.** Session77821 is terminal: `ui-baseline-2`, boot `7ed9e2e81b8d3843853ab0858bb53826`, firmware `6079c55-dirty`. Final serial summary, four isolated baseline assessments, live-audio/ingress, synthetic speech and FFT pass. No event gaps or capture errors; keep-awake assertions ended with collection. This is historical passing evidence, not the currently flashed candidate.

Display result: 1,819 distinct states in 60 seconds, 30.299 software panel submissions/s; frame p95/max47.168/50.185ms, state-change-to-submit p9519.167ms, no coalesced/repeated states or observer overflow. LVGL runtime4.97%, stack margin4316B. These are **software submissions**, not physical presentation or physical-input latency.

`ui_ingress` wraps the real panel draw and preserves its arguments, return and BSP completion callbacks. LVGL render-start latches the current animation ID; flush-start supplies the last-flush marker. All observer/context mutations occur under the BSP display lock; fixed PSRAM rows cannot grow. Partial flushes count as one render. The timer compensates relative LVGL timer drift against absolute33ms device deadlines; invalidated regions are checked every20ms, then the configured refresh period is restored. Future combined work must preserve these ownership rules.

## Retain these failures and limits

- `ui-baseline-1` (session72207 terminal) has two serial sequence gaps and no IMU export. Mac power transitions were saved. Its 28.570fps display result met interval limits but missed30fps. The first host assessor omitted the rate gate; retain its initial result and `-corrected-assessment.json`, which fails. Both candidate source snapshots match their respective manifests. Do not relabel the original run as passing.
- `camera-baseline-1` has an original inconclusive summary caused by misspelled required-check name `ina226226_manufacturer`. Preserve it and its manifest; independent `corrected-check-summary.json` passes the actual correctly selected events. Its resource assessment adds strict CPU/stack/SRAM checking.
- `software-restarts-1` exposed an LVGL startup race. Startup object construction now holds the BSP display lock. `software-restarts-2` passes ten ESP_RST_SW boots; **not cold starts**.
- Earlier PPA alignment failure, radio-startup failures and headphone attachment/reset ambiguity remain in .01 Observed. Full-frame PSRAM display buffers, compatible task SRAM and deferred hosted-radio initialization fixed the recorded cases; do not undo those fixes.
- Earlier vendor IMU helpers ignored Bosch init/enable/read errors. `imu_checked` reuses the BSP device captured at `bmi270_init`, verifies enable and ODR/range readback, and never publishes failed reads. The100Hz baseline polls latest registers from200Hz hardware; intermediate samples are intentionally unretained, not FIFO losslessness.

## Other established evidence

Native camera acquisition:1280×720 RGB565 at~30fps, 60-second runs with observed backup-buffer starvation/completion accounting. Runtime rejects640×480. Camera receive is bounded; the final owned image is exported only after streaming stops. Camera+JPEG now passes with four buffers/FIFO; live preview/network and full combined acceptance remain open.

Audio: repeated6000×480-frame48kHz baselines with raw immutability, separate16kHz speech and FFT2048 every2400frames; isolated read/consumer timing and driver counters pass. Live pairs retain141 block hashes/ranges each; independent derived-reference comparison passes. Synthetic speech has24pairs and FFT12fixtures. Current consumers are synchronous and retain copies, not raw pointers; future asynchronous ownership requires new evidence.

Physical microphone fixture is complete in `audio-ingress-1/microphone-position.json`: three near-USB/headphone-hole takes favor rawslot2; three farther-hole takes favor rawslot0, with modest margins/cross-pickup. User recognizes slots0/2 (0best) and no phrase in1/3. Keep physical-position names: factory MIC-L/R comments and annotated-photo naming disagree when combined. Earlier batch count mismatch is retained. Headphones reproduce0/2 in both ears at better level; speaker remains faint. Requested gain24dB is not hardware readback; no calibration claim.

ADRs0003–0007 are Active: pinned factory/IDF and BSP ownership, capture completion, radio lifecycle, immutable raw/owned speech, and bounded camera FIFO. Reserved0001/0002 were proposals, not revoked decisions. Do not mistake these bounded decisions for final combined architecture.

## Next work

1. Add a reproducing test for the queued-DMA JPEG timeout in `jpeg-lifecycle-review.md`. Inspect `jpeg_pipeline.cpp`, pinned `jpeg_encode.c` and `dma2d.c`; do not release/reuse/free a potentially pending DMA source. Establish cancellation/quiescence or fail closed, and cover partial allocation and worker shutdown before broader concurrency.
2. Then add preview and progressive camera/audio/IMU/UI concurrency, explicit bounded queues and counted preview coalescing. Raw-audio loss remains failure. Four buffers do not reduce source hash/copy cost; preserve provenance and measure combined contention/memory. Re-run all regressions after firmware changes. Historical research is in baseline `jpeg-source-notes.md`.
3. Prepare bounded host backpressure receiver and Mac Python mock-agent protocol while device Wi-Fi waits for user reconnection. Keep configurable endpoint, IDs/deadlines/cancel/idempotency and service-side credentials. .04 mock tests do not substitute for30 live turns or3 guided A/B ratings.
4. Execute all original .02 gates: isolated stages, three10-minute combined runs,100 physical input events/run,10-second receiver stall, mode cycles and memory return. .01 still needs true cold starts/storage and remaining capability limits; .03 needs acoustic/load/SD evidence; .05 power/wake/recovery is unbuilt. Follow-ups requiring the user are in TODO.md.

User intent remains the handheld Ask → measure → feedback → adjust → discover loop in [vision](vision.md), with Explore/Investigate/Compare and inspectable capabilities. Prioritize that interactive outcome; unattended diagnostic passes are groundwork. IMU motion describes the instrument unless physically coupled to the object. The user is an experienced programmer learning embedded/C++; explain ownership/timing when it helps their decisions.
