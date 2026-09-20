# Tricorder agent handoff

Updated: 2026-09-20

G-0001 is **In progress**. Authoritative gates and concise outcomes are in [milestones](planning/milestones.md) and [G-0001](planning/plans/G-0001-trustworthy-live-investigation.md). .01 hardware, .02 isolated workloads and .03 audio integrity have evidence; full acceptance is unverified. .04/.05 remain Not built. Preserve original thresholds, counts and failed runs. Observed sections are append-only; details belong in commits/private evidence.

The user is **away** and requests autonomous progress with follow-ups in [TODO.md](TODO.md). No physical input is pending. Continue JPEG, combined-workload and Mac mock-service preparation; do not repeatedly ask for unavailable equipment or physical actions.

## Device and execution

- Correct Tab5: USB serial `E8:F6:0A:E2:E0:0E`, most recently `/dev/cu.usbmodem4`, P4 v1.3, 16 MB flash, 32 MB PSRAM, ST7121. Rediscover ports before flashing. `/dev/cu.usbmodem1101` is a different device.
- Battery pack installed. No microSD installed or available. Wi-Fi credentials are RAM-only and the current boot is not associated; the user previously completed three matched LAN exchanges over 2.4 GHz.
- Verified original flash backup (two matching full reads), restore instructions, artifacts and private captures are in `.local/runs/20260920-baseline/`. Do not commit captures, backup contents or secrets. Both factory builds were explicitly approved and booted.
- Bootstrap: `python3 tools/bootstrap.py`; build: `tools/idf.sh -C firmware build`; tests: `python3 -m unittest discover -s tests -q`. Toolchain/USB/git writes required sandbox escalation here. No push requested.
- **Prevent host sleep during serial runs:** prefix the collector with `/usr/bin/caffeinate -is`; its assertions automatically end with the collector. A sleeping Mac lost whole USB export intervals while the battery-powered Tab5 kept running. Do not infer successful device continuity from a missing host interval.
- Current diagnostic starts sequential 60-second camera/audio/motion/display baselines plus short live and synthetic audio fixtures; allow six minutes. Manual record/restart/audio controls remain available. Reopening USB can reset the board. Never restart a process merely because an observation timeout expires; inspect its exact handle/state first.

## Current verified build

**92 host tests and P4 build pass.** Current source/artifact manifest: baseline `ui-baseline-build-2-manifest.json`; archived binary/ELF/map and exact source snapshot: `ui-baseline-build-2-artifacts/`. Source hashes are authoritative despite the dirty version string.

**No active collector.** Session77821 is terminal: `ui-baseline-2`, boot `7ed9e2e81b8d3843853ab0858bb53826`, firmware `6079c55-dirty`. Final serial summary, four isolated baseline assessments, live-audio/ingress, synthetic speech and FFT pass. No event gaps or capture errors; keep-awake assertions ended with collection. Device is idle at the diagnostic screen.

Display result: 1,819 distinct states in 60 seconds, 30.299 software panel submissions/s; frame p95/max47.168/50.185ms, state-change-to-submit p9519.167ms, no coalesced/repeated states or observer overflow. LVGL runtime4.97%, stack margin4316B. These are **software submissions**, not physical presentation or physical-input latency.

`ui_ingress` wraps the real panel draw and preserves its arguments, return and BSP completion callbacks. LVGL render-start latches the current animation ID; flush-start supplies the last-flush marker. All observer/context mutations occur under the BSP display lock; fixed PSRAM rows cannot grow. Partial flushes count as one render. The timer compensates relative LVGL timer drift against absolute33ms device deadlines; invalidated regions are checked every20ms, then the configured refresh period is restored. Future combined work must preserve these ownership rules.

## Retain these failures and limits

- `ui-baseline-1` (session72207 terminal) has two serial sequence gaps and no IMU export. Mac power transitions were saved. Its 28.570fps display result met interval limits but missed30fps. The first host assessor omitted the rate gate; retain its initial result and `-corrected-assessment.json`, which fails. Both candidate source snapshots match their respective manifests. Do not relabel the original run as passing.
- `camera-baseline-1` has an original inconclusive summary caused by misspelled required-check name `ina226226_manufacturer`. Preserve it and its manifest; independent `corrected-check-summary.json` passes the actual correctly selected events. Its resource assessment adds strict CPU/stack/SRAM checking.
- `software-restarts-1` exposed an LVGL startup race. Startup object construction now holds the BSP display lock. `software-restarts-2` passes ten ESP_RST_SW boots; **not cold starts**.
- Earlier PPA alignment failure, radio-startup failures and headphone attachment/reset ambiguity remain in .01 Observed. Full-frame PSRAM display buffers, compatible task SRAM and deferred hosted-radio initialization fixed the recorded cases; do not undo those fixes.
- Earlier vendor IMU helpers ignored Bosch init/enable/read errors. `imu_checked` reuses the BSP device captured at `bmi270_init`, verifies enable and ODR/range readback, and never publishes failed reads. The100Hz baseline polls latest registers from200Hz hardware; intermediate samples are intentionally unretained, not FIFO losslessness.

## Other established evidence

Native camera acquisition:1280×720 RGB565 at~30fps, 60-second runs with observed backup-buffer starvation/completion accounting. Runtime rejects640×480. Camera receive is bounded; the final owned image is exported only after streaming stops. No live preview/JPEG/network acceptance yet.

Audio: repeated6000×480-frame48kHz baselines with raw immutability, separate16kHz speech and FFT2048 every2400frames; isolated read/consumer timing and driver counters pass. Live pairs retain141 block hashes/ranges each; independent derived-reference comparison passes. Synthetic speech has24pairs and FFT12fixtures. Current consumers are synchronous and retain copies, not raw pointers; future asynchronous ownership requires new evidence.

Physical microphone fixture is complete in `audio-ingress-1/microphone-position.json`: three near-USB/headphone-hole takes favor rawslot2; three farther-hole takes favor rawslot0, with modest margins/cross-pickup. User recognizes slots0/2 (0best) and no phrase in1/3. Keep physical-position names: factory MIC-L/R comments and annotated-photo naming disagree when combined. Earlier batch count mismatch is retained. Headphones reproduce0/2 in both ears at better level; speaker remains faint. Requested gain24dB is not hardware readback; no calibration claim.

ADRs0003–0006 are Active: pinned factory/IDF and BSP ownership, capture completion, radio lifecycle, and immutable raw/owned speech. Reserved0001/0002 were proposals, not revoked decisions. Do not mistake these bounded decisions for final combined architecture.

## Next work

1. Implement/test native JPEG encoding and fresh-frame provenance, then progressive camera/audio/IMU/UI concurrency. Source findings: baseline `jpeg-source-notes.md`. IDF hardware JPEG supports RGB565; use a single owned engine, aligned bounded output, valid quality/subsampling and explicit timeout. Validate source byte extent yourself. Preserve encoder failure/cleanup evidence; independently decode saved JPEGs. A static-frame encode benchmark is not fresh acquisition every2seconds.
2. Do not hold either of the two camera capture buffers during encoding or serial/network export. Establish copied-frame ownership and explicit counted preview coalescing. Raw-audio loss remains failure. Test allocation/queue saturation/lifetimes before combined runs.
3. Prepare bounded host backpressure receiver and Mac Python mock-agent protocol while device Wi-Fi waits for user reconnection. Keep configurable endpoint, IDs/deadlines/cancel/idempotency and service-side credentials. .04 mock tests do not substitute for30 live turns or3 guided A/B ratings.
4. Execute all original .02 gates: isolated stages, three10-minute combined runs,100 physical input events/run,10-second receiver stall, mode cycles and memory return. .01 still needs true cold starts/storage and remaining capability limits; .03 needs acoustic/load/SD evidence; .05 power/wake/recovery is unbuilt. Follow-ups requiring the user are in TODO.md.

User intent remains the handheld Ask → measure → feedback → adjust → discover loop in [vision](vision.md), with Explore/Investigate/Compare and inspectable capabilities. Prioritize that interactive outcome; unattended diagnostic passes are groundwork. IMU motion describes the instrument unless physically coupled to the object. The user is an experienced programmer learning embedded/C++; explain ownership/timing when it helps their decisions.
