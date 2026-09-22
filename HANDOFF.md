# Tricorder agent handoff

Updated: 2026-09-22 — transport hardening, live text probes and completed physical A/B.

## Current checkpoint

The fresh **8-inch A → 16-inch B physical mock trial completed**. The operator
reported “Comparison appeared”; independent raw/hash/ingress and transcript/ACK
checks pass. B/A digital RMS is **−3.8894 dB** (B quieter), with no clipped samples.
This is one completed physical trial on the transport candidate, not live speech
or full acoustic acceptance. The operator confirmed audible MacBook built-in
speakers, a quiet room and measured placements before recording; the exact ruler
or tape was not specified. Preserve that fixture limitation.

Evidence below is relative to `.local/runs/20260922-transport-resume/`:

- Physical boot `92ca13cf587e052c0a184f6033f42c4e`, session
  `ab-37d8b855eaf9b6a50662cc17bcd1f9ad`: `physical/assessment-1.json`,
  `physical/operator-1.json`, `physical/fixture.json`, `physical/mock/` and
  `physical/serial/`. `physical/interrupted-trial.json` retains the earlier
  adjustment timeout during a conversation interruption; it remains incomplete.
  The finalized serial summary is **FAIL** for malformed instrumentation, with
  all three startup checks passing and no integrity errors listed. Preserve that
  summary separately from the passing A/B assessment; no full log-integrity pass.
- Bounded TCP completion is implemented below WebSocket framing, retaining the
  original timeouts and cancellation behavior. Native short-write tests and normal
  device SD replay pass (`candidate/assessment.json`). The 80-ms/chunk receiver
  trial fails explicitly at the two-second write timeout (`slow-candidate/`).
  The historical B failure still lacks send counts: its exact cause is unproven.
  The successful new physical trial does not erase it or establish reliability.
- The asynchronous text adapter supports OpenRouter `openai/gpt-5.6-sol` through
  the existing service/evidence contract. Two approved real summary calls pass in
  **3.21 / 2.93 seconds** (`openrouter-smoke.json`). Only verified summaries,
  capture references and fixture notes were sent. The host owns measurements;
  provider failure never silently falls back to mock. Speech remains unimplemented.
- **192 host tests pass** (`tests-3.txt`), including native sanitizer and localhost
  WebSocket checks. P4 build/flash pass (`build-3.txt`, `flash-1.txt`).
  `candidate-manifest.json` and `candidate-artifacts/` identify the flashed image;
  later host/docs changes are captured separately in `commit-checkpoint.json`.
- Current network was provisioned from ignored `.env.local.newnet`; the ignored
  `.env.local.openrouter` contains the provider key. Never print or commit values.
  Initial network failures remain alongside successful provisioning/LAN checks.

The completed trial has been closed: tone finished, collector finalized and mock
service stopped. The candidate remains flashed. The user requested a local commit;
no push. G-0002, G-0001 and M-0001 remain **In progress** with unchanged gates.
The sections labeled earlier/previous checkpoints retain historical claims only.

## Earlier checkpoint — SD recovery and replay

**Latest physical retry:** the memory-fixed image stayed running, saved A and B
to SD, then displayed **Incomplete** while starting B's upload. The mock received
A and its guidance/ACK, but no B metadata. Both SD recordings independently pass
raw/hash/141-block ingress checks; the original exchange remains incomplete.
Evidence: `.local/runs/20260922-sd-ab-2/`, source boot
`b936e25692766aba3758affc26b1bd55`, session
`ab-2f45739e04fe71cdd5302938fec1a3b7`. The ordinary serial summary retains one
malformed instrumentation line; named startup checks pass and no reboot/panic was
observed. The overall SD downloader retains an unrelated older synthetic-file
HTTP failure; `sd-recovery-assessment.json` is scoped to the two verified real files.

**SD replay now exercises the same device upload/guidance/comparison flow without
new acquisition.** The replay-only server and independent assessor explicitly
label it; original boot/session/timestamps/proofs and raw bytes are preserved.
Normal and deliberately slowed (45 ms/chunk) device replays completed with
byte-for-byte original SD agreement: `.local/runs/20260922-sd-replay-{1,2}/`.
Replay 1 serial summary passes; replay 2 retains an attachment-line FAIL despite
its independently passing complete A/B transcript. Replay 3 verifies the reusable
collector command (`20260922-sd-replay-3/assessment.json`), also with a passing
independent transcript and a retained attachment-line serial FAIL.
These do not turn the failed
physical run into a pass. The recorded digital RMS ratio is +0.9380 dB B/A,
contrary to the distance hypothesis; approximate phone-gauge placement and
unreported noise/source audibility do not support an acoustic acceptance claim.

The original restart remains separately retained under `20260922-sd-ab-1`.
Its fix reduces reducer metadata retention from 62,643 bytes to under 2 KiB and
uses PSRAM for SD/HTTP scratch. That crash did not recur in the physical retry.
The newer diagnostic firmware adds replay and numeric send-result logging;
`20260922-sd-ab-2/replay-manifest.json` / `replay-artifacts/` identify its P4
build/flash. **180 host tests pass** after the reusable collector and independent
replay-label checks. See `tests-final.txt` and the final checkpoint manifest.
The original B upload failure was not reproduced by the three replays; its exact
transport cause is still open. Do not claim a connection fix or change deadlines.
No further physical repeat is requested at this checkpoint. Test processes are
stopped; the tone is off. The user requested review and a local commit; no push.
The tested image was built from parent `7bd5211` with uncommitted changes;
the archived hashes identify it independently of the eventual commit ID.
The earlier SD setup evidence below remains valid for its original bounded scope.

### Earlier SD setup validation

The installed microSD card now supports **persistent Wi-Fi/endpoint setup, verified
local A/B capture archives and LAN downloads**. Credentials from the user's
`env.local.northbank` (no leading dot) were sent over USB, saved on SD and loaded
successfully after reboot. The Tab5 joined at **10.0.13.116**; Mac **10.0.13.37**.
The saved mock endpoint is `ws://10.0.13.37:8765/`. Rediscover addresses before
future trials. No Mac hotspot was needed. The source file and all `.env.*` /
`env.local.*` files are ignored; credentials were not embedded in firmware or
found in retained logs. SD config and its previous-version fallback are plaintext.

**175 host tests pass**, including native ASan file/config recovery checks and
real localhost WebSocket tests. P4 builds and flashes pass. The final storage
implementation passes startup SD/radio/HTTP checks, three isolated LAN challenges,
five full-size synthetic SD downloads with matching SHA-256, and five negative
HTTP checks excluding credentials, traversal and partial files. SD write plus
readback is about **3.01 seconds per 1,152,000-byte capture**; larger buffers did
not materially improve this. Downloads are intended between trials.

All evidence is under `.local/runs/20260922-sd-testing/`: `tests-4.txt`,
`build-5.txt`, `flash-2.txt`, `final-boot/summary.json`, `lan-final/summary.json`,
`download-final/summary.json`, `route-isolation.json`. `final-manifest.json` and
`final-artifacts/` identify that tested image and 146 source/config/build files.
A subsequent **text-only** correction removed the stale no-SD screen message and
clarified manual Wi-Fi edits; `build-6.txt` / `flash-3.txt` and `final-ui-manifest.json` / `final-ui-artifacts/` identify that earlier image. No functional SD/network change followed
the passing tests above at that earlier checkpoint. These artifacts precede the
memory fix and replay image identified above. `final-ui-boot/summary.json` confirms that
image's startup checks and saved Wi-Fi reconnect (boot
`851cfd27dd926f582bac30a28b9c1e83`); its full-size save took 2.50 seconds.
`checkpoint.json` records final artifact agreement. No trial processes remain running.

Retain the initial failed attempts: `provision-1/events.json` saves successfully
but sees transient AP-not-found; `reboot-1` reconnects using saved settings but
its ordinary summary fails due to a serial line interrupted by the reset banner.
`lan-1` is unreachable; `lan-2` has one timeout during concurrent bulk download.
Do not replace them with later passes.

**G-0002 remains In progress.** Neither new physical SD-backed attempt completed the A/B protocol.
The existing local Record controls now archive raw bytes and original metadata
before upload; completed SD files survive a later network failure. No overwrite
or automatic capture deletion occurs. Metadata commits last; raw-only and `.part`
files do not establish completion. Config recovery is host-tested for interrupted
rename states and corrupt-current fallback, not verified through physical power
loss. Live-provider/speech work remains deferred. See the [SD setup and export
procedure](planning/guided-ab-protocol.md#sd-assisted-testing--2026-09-22).

Next investigation: use the retained SD pair and transport diagnostics to isolate
the intermittent B upload failure. A later physical retry needs confirmation that
the source tone is audible and the placement/noise conditions are controlled.
Keep all original failures and the three earlier successful physical loops distinct.
Replay does not operate the microphones; fresh captures still require local Record.

## Previous checkpoint — 2026-09-21

The Tab5 now runs a preset, text-only **Guided A/B** investigation through the Mac mock service: capture A → evidence-linked guidance → operator adjustment → capture B → verified comparison. Three settling-corrected developmental loops completed. Delayed replies, cancellation, service disconnection and fresh-session recording/guidance recovery have retained evidence. All trial services, serial collectors and tone players are stopped; trial-4 firmware remains flashed. No push was requested or performed.

**G-0002 remains In progress.** The user explicitly replied “Defer live-provider work for now” when asked which model/speech provider to use. That means actual model integration, spoken input/output and three operator-rated live loops remain deferred; this is not a pause on all project work. G-0001 and M-0001 are also incomplete. No original threshold, run count or failed evidence is waived. [G-0002.01's requirement disposition](planning/plans/G-0002.01-guided-ab-slice.md#requirement-disposition-at-the-mock-checkpoint) is the current acceptance map; its Observed history is append-only.

This checkpoint adds the device implementation to parent `ef38657` (host mock checkpoint). The tested binary was built before this commit and reports `ef38657-dirty`; exact archived hashes identify the tested image. Raw audio, serial logs, build artifacts, private sdkconfig and local endpoint settings stay under ignored `.local/` or `firmware/sdkconfig` and are not committed.

## Resume here

1. Read the current checkpoint, [G-0002.01](planning/plans/G-0002.01-guided-ab-slice.md),
   [protocol/setup](planning/guided-ab-protocol.md), [ADR-0011](planning/adrs/ADR-0011-bounded-tcp-write-completion.md)
   and [ADR-0012](planning/adrs/ADR-0012-live-prose-over-verified-summaries.md).
   Retain the existing device-owned flow and local Record controls.
2. Continue instrumented transport checks if failures recur. Preserve originals,
   partial transfers and timeouts. Complete fixture characterization and actual
   panel/pending-cancel timing before claiming formal mock acceptance.
3. Text provider selection and credentials are complete. Next integrate speech
   into the same flow and collect three live handheld loops with responsiveness
   and usefulness feedback. No speech provider/codec has been adopted; choose it
   before implementing or sending audio. The two summary probes are not live loops.
4. Resume G-0001 hardening on the shared implementation: full simultaneous
   camera/preview/audio/FFT/IMU/UI, backpressure, memory return, storage, power and
   original interaction statistics. Before ten-minute camera runs, replace the
   diagnostic 6 MiB/30-JPEG retention pool with bounded recycling/streaming.
   Preserve the JPEG fail-stop guard; fault injection is not a startup routine.

## Earlier implementation and validation — 2026-09-21

- `firmware/main/investigation{,_protocol,_capture}.cpp` and `investigation_wire.h`: native state/evidence guard, bounded IDF WebSocket transport, LVGL controls and one raw capture at a time through the existing media owner. Only local controls initiate capture; terminal states require a fresh session. Endpoint entry now has a visible keyboard with verified panel bounds.
- Shared fixture: MacBook built-in speakers, continuous 1000 Hz, **30% system volume**, **8 inches / 16 inches** to the farther microphone hole (slot 0), same orientation. Use imperial measurements going forward. The user confirmed measured distances and no noticeable background noise for the two resumed repeats. The first corrected run has incomplete fixture notes; do not retroactively call all three pre-frozen acceptance runs.
- Capture: 48 kHz, four-slot signed 16-bit raw, requested 24 dB gain, explicit 24,000-frame/0.5-second settling prefix, then 144,000 frames/three seconds retained. Raw SHA-256, per-block hashes/timestamps and full-epoch counters accompany upload. The Mac recomputes measurements; the device validates results and capture/request/ACK identity. Settling is a versioned experiment setting, not calibrated acoustics.
- `tools/investigation_evidence.py` independently assesses complete saved A/B sessions. `tools/investigation.py` verifies firmware ingress proofs. Host/native failure tests include cancellation, stale/expired replies, framing and capture cleanup.
- **172 tests pass**, including ASan native checks and both real localhost WebSocket tests: `tests-settling.txt`. **P4 build and flash pass**: `build-trial-4.txt`, `flash-trial-4.txt`. No implementation change since that validation. The saved test log includes expected negative-fixture output; its unittest result is OK with no skips.
- Exact 72-file source/config/artifact snapshot: `trial-4-manifest.json`, `trial-4-artifacts/`. All 72 still match at closeout. Binary SHA-256: `71ee210fb05dd835745bbb13a49a2ddc2bc5e11a6fc39266dbcd7bfcd63e1cf8`. These filenames and all evidence below are relative to `.local/runs/20260921-g0002-device/`.

## Evidence index

| Trial | Result and retained evidence |
| --- | --- |
| Initial UI / first physical loop | Off-panel keyboard prevented endpoint entry; corrected before later trials. `development-1-*` retains the subsequent complete loop whose +14.1000 dB result was dominated by startup transients. Technical transfer passed; acoustic interpretation failed. Never delete or replace it. |
| Settling-corrected loops | `development-2/3/4-{assessment,window-analysis,operator}.json`: three technical passes, B/A −6.9860 / −7.5752 / −9.9557 digital dB, no clipping or original startup spikes. Runs live under `mock-trial-2` and `mock-trial-3`. `repeat-fixture-clarification.json` supplements the last two operator records. |
| Five-second replies / pending cancel | `delay-cancel-1-assessment.json`, `mock-delay-1`: reply delays 5.0201/5.0298 seconds; a separate pending turn received cancel/cancelled and no late guidance. Operator reported prompt cancellation. Its device timing was missed when collector 5 reached its duration limit. Tone had ended; control trials are not acoustic comparisons. |
| Capture cancellation | `capture-cancel-1-assessment.json`: recording A cancelled before upload; request-to-owner-stop 15.921 ms. This is not panel/playback or pending-turn timing. |
| Disconnect / recovery | `disconnect-1-assessment.json`, `reconnect-2-assessment.json`: service closed during a pending turn, device showed Offline, listener restarted after 5.002647 seconds, and a fresh session recorded A and received independently verified guidance/ACK before Cancel. Old session stayed Offline. Restart was operator-paced; no automatic five-second recovery claim. `reconnect-1-ready-cancel-assessment.json` preserves the earlier handshake-only attempt. |
| Serial integrity limitations | Trial 5 ordinary FAIL retains a wrong declared observation boot plus a malformed attachment line. Trial 6 ordinary FAIL retains one malformed line before the new ROM banner. Separate parsed-current-boot assessments show continuous sequence/time and named startup passes only; they do not repair original logs or missing timing. |
| Closeout | `final-checkpoint.json`: all trial processes stopped and 72 source/build hashes match. Latest observed boot `9b7157204331e6b81fceb8b95806e446`; recovery session `ab-0b7963eda0072dfdbba664eba30f25a8`. `disconnect_fixture.py` and its event log retain the controlled outage procedure. |

Detailed chronology, session IDs, limitations and architecture disposition remain in [G-0002.01 Observed](planning/plans/G-0002.01-guided-ab-slice.md#observed). [ADR-0010](planning/adrs/ADR-0010-device-owned-ab-lan-experiment.md) adopts the bounded mock architecture only. Earlier ADR-0003 through ADR-0009 and all G-0001 gates remain in force.

## Device and execution

- Correct Tab5 USB serial **E8:F6:0A:E2:E0:0E**, last found at `/dev/cu.usbmodem1101`, P4 v1.3, 16 MB flash, 32 MB PSRAM, ST7121. Rediscover with `.tools/python-env/bin/python -m serial.tools.list_ports -v` and match identity before opening. `/dev/cu.usbmodem11101` is another board.
- **Opening USB serial can reset the Tab5**, even without an explicit reset. Keep one collector open through an operator trial and use a suitable bounded duration. SD-provisioned Wi-Fi/endpoint settings reload after ordinary reset; manual screen edits are temporary. Latest LAN addresses: Mac `192.168.0.44`, Tab5 `192.168.0.66`; recheck before use.
- Current private sdkconfig has `CONFIG_TRICORDER_GUIDED_AB_STARTUP=y` and an editable initial endpoint. This skips automatic media diagnostics and waits for manual A/B after board/display/radio startup. Skipped stages do not pass diagnostic gates. JPEG fault injection stays disabled. The default build option remains off.
- Start the mock using a new evidence directory, join Wi-Fi and open Guided A/B. **Start mock connects; the separate Record A button starts acquisition.** After guidance, Confirm position B enables the separate Record B button. Follow [protocol/setup](planning/guided-ab-protocol.md) for exact commands and bounds.
- Full host tests: `.tools/investigation-env/bin/python -m unittest discover -s tests -q` (this environment includes the pinned WebSocket dependency). Build: `tools/idf.sh -C firmware build`. Bootstrap: `python3 tools/bootstrap.py`. USB, localhost listeners and builds may need sandbox escalation. Do not rebuild/reflash just to identify the current checkpoint.
- Prefix physical collectors with `/usr/bin/caffeinate -is` and set explicit spec/revision/workload metadata. Host sleep previously lost USB export intervals; missing intervals cannot establish continuity.
- Battery pack and microSD installed. Verified full flash backups and restore procedure remain in `.local/runs/20260920-baseline/`. Keep captures/backups/secrets private. User/equipment follow-ups are in [TODO.md](TODO.md).

The sections below are historical checkpoints, not current process or firmware state.

## Earlier validated checkpoint: owned live preview passes

**121 host tests and P4 compilation pass.** At that earlier checkpoint, flashed firmware was `8efbc8c-dirty`, with exact sources/config/binary/ELF/map in `.local/runs/20260921-camera/preview-wake-1-artifacts/` and `preview-wake-1-manifest.json`. At that closeout, all 59 firmware/build files matched that manifest. Binary SHA-256: `58e12983af2d25c5ae07c27a921691e545657f8c94832c186959d19559e8874a`. Deliberate JPEG fault injection remains disabled.

`preview-wake-1`, boot `1c505e37876dc30ed1002fc0595d110f`, collector **32001 terminal**, passes final serial and all ten independent assessments. Native camera:1,800 ordered frames29.999fps, zero reuse/loss, maximum buffer hold80.707ms. Preview:900 produced,873 actual panel-submitted states14.522fps,27 explicitly replaced pending frames, zero selected-but-unrendered or repeated states. First submission121.201ms; gap p95/max109.019/186.045ms, source-age p95/max97.744/184.533ms. Final preview is visually readable and every byte matches independent downsampling of the retained native source. This half-rate preview is not the30fps animated-UI acceptance test.

All30 JPEGs decode with matching native/copy/post hashes; worker p95/max139.945/140.118ms. Camera PSRAM free/largest minima4,865,136/4,718,592B; JPEG/LVGL stack margins6,288/4,496B at the camera snapshot. Later audio6,000 blocks, IMU6,000 polls100Hz and UI1,819 states30.302fps p95/max47.116/49.179ms pass, as do live/ingress/synthetic speech and reference-2 FFT. No serial gaps, incomplete captures or capture errors. Still a camera/preview/JPEG epoch followed by sequential baselines, not full combined acceptance.

`preview_queue.h` owns three460,800-byte derivative buffers: writing, pending and displayed. A producer may replace only the pending slot; the displayed source stays immutable between renders. The pinned one-unit synchronous LVGL renderer holds the BSP lock; panel DMA reads separate LVGL draw buffers. Core1 rendering avoids preempting the core0 camera owner. Explicit `lvgl_port_task_wake` follows preview/animation timer installation from another task, since creating a timer does not interrupt the port's old idle wait. [ADR-0009](planning/adrs/ADR-0009-owned-preview-and-render-placement.md) records this bounded decision. Changing renderer/backend requires new source-lifetime evidence.

Preserved failures: `preview-1`, boot `38537f7cc496b9999b8aadea5771d4ff`, collector **72675 terminal**, loses seven native completions (1,793 rows), has223ms preview gap/206ms age, and skips later sustained stages. Camera/JPEG/preview independent assessments fail; live/synthetic fixtures pass. `preview-core1-1`, boot `12f2f37b64ac049e51172aced179bad8`, collector **45375 terminal**, fixes camera loss and passes final serial plus all other regressions, but independent preview FAILS on304.086ms first submission. Both exact artifacts/manifests and original assessments remain intact. `workload-scope.json` identifies .02 despite the generic collector manifest's historical .01 default; add an explicit spec/revision option before future combined captures rather than overwriting old manifests.

## Previous checkpoint: JPEG error-path fail-stop verified

**112 host tests and P4 compilation passed at that checkpoint.** Previously flashed normal firmware was `9857c89-dirty`, exact sources/config/binary/ELF/map and hashes in `.local/runs/20260921-camera/jpeg-guard-2-artifacts/` and `jpeg-guard-2-manifest.json`. Its binary SHA-256 is `859f2a48288bf52bcaf245a5ce2ecb9210794e3e42ab1124a1a70de73f9a7d12`. Earlier `jpeg-guard-1` artifacts are an unflashed normal build; do not confuse them with that tested image.

Normal `jpeg-guard-2`, boot `ecfb1d7d3fcb637a7db222964855f63e`, collector **31181 terminal**, passes final serial and all nine independent assessments. Camera: 1,800 consecutive frames, 29.999 fps, zero reuse/order/tail/loss; frame p95/max33.335/33.460ms. All30 JPEGs decode and source/copy/post-hashes/raw witness agree; worker p95/max89.136/90.255ms, source hash/copy p9534.305/34.103ms. PSRAM free/largest minima7,289,476/7,208,960B; JPEG stack margin6,256B. Audio6,000 blocks, IMU6,000 polls100Hz, UI1,819 states30.299fps p95/max47.135/49.187ms; live/ingress/synthetic speech and reference-2 FFT pass. Final JPEG is visually readable. Still sequential, not full concurrent or physical-input acceptance.

User explicitly approved the controlled fault test after automatic review initially rejected it. `jpeg-timeout-1`, collector **49086 terminal**, captures boot `92c66a8e4aa0b988fee6372d34c7c759` arming the sole-reorder-channel blocker, real driver timeout, exact guard panic, then boot `c24dfb36d735a09a6336467c44e9e0e2` with reset reason4/PANIC skipping rearming and initializing JPEG. **Ordinary summary remains FAIL**; `expected-fault-assessment.json` separately passes only that ordered sequence. Exact fixture sources/artifacts/manifest, raw logs and callsite symbolization are retained; no unguarded unsafe hardware run was performed.

Normal firmware was then restored with flash hash verification. `jpeg-guard-restored-1`, boot `c98ed075b767f2217f4f3dfd628c1cfb`, collector **20107 terminal**, passes20-second startup checks with no fixture events or panic. This is a startup confirmation of the already-tested image, not another full regression.

The guard tracks the sole encoder task and wraps `dma2d_force_end` before the pinned driver's `err1` returns or touches a stale channel. Other tasks/ISRs delegate unchanged; overlapping encoder calls are rejected. [ADR-0008](planning/adrs/ADR-0008-jpeg-error-path-fail-stop.md) records this fail-stop policy, not recoverable timeout handling. Host tests cover seven resource-failure points, ten lifecycles/300 encodes, retention saturation, source damage/safe codec errors and destruction during active encoding under AddressSanitizer. Mock codec/resource tests do not establish vendor-internal allocation cleanup or device fragmentation/mode-cycle memory return. Full zero-crash combined gates remain unchanged.

## Previous checkpoint: FIFO camera/JPEG and sequential regressions pass

**103 host tests and the P4 build passed.** Previously flashed firmware was `8c98c00-dirty`, with exact sources, binary/ELF/map and hashes archived in `.local/runs/20260921-camera/jpeg-fifo-1-artifacts/` and `jpeg-fifo-1-manifest.json`. Historical archive hashes matched that checkpoint; current firmware adds the guard above.

`jpeg-fifo-1`, boot `0abb801259aea44bed22ee77eef014b3`, collector session **85731 is terminal**, stopped cleanly via STOP. Final serial summary, all four sustained baselines, JPEG, live-audio/ingress, synthetic speech and FFT pass independently. No serial gaps, capture errors or incomplete captures; all 30 JPEGs decode with matching independent source/copy/post-encode hashes and final raw witness. Final JPEG is visually readable. FFT must use `.local/runs/20260920-audio-reference-2`, whose impulse peak is correctly non-unique.

Camera: 1,800 consecutive rows at 29.999 fps over 60.001 s, zero reuse/order errors or unaccounted completions; frame p95/max 33.335/33.366 ms. JPEG source hash/copy p95 35.208/34.121 ms; worker p95/max 91.972/92.298 ms. Maximum camera-buffer hold remains 69.405 ms; four bounded buffers absorb this burst. PSRAM free/largest minima 7,289,732/7,208,960 bytes; JPEG stack margin 6,368 bytes. UI: 1,819 states at 30.302 software submissions/s, p95/max 47.216/49.960 ms. Audio: 6,000 blocks; IMU: 6,000 polls at 100 Hz. These are isolated/sequential results, not combined-load or physical-input acceptance.

Mechanism: backup is disabled in the pinned CSI configuration. When the queued list empties, the shim supplies the active DMA buffer again and suppresses delivery; the old observer still counted its completion. It also pushes done buffers onto a newest-first list. `camera_receive.cpp` removes the oldest done element under the original stream lock, taking the existing counting semaphore and preserving free flags; it delegates other video devices to the original path. Private header dependency and linker inclusion are explicit. `camera_ingress` counts active-buffer reuse. Stop-tail counts use a separate pre-STREAMOFF snapshot; the final JPEG hash/copy occurs after stopping. [ADR-0007](planning/adrs/ADR-0007-bounded-camera-fifo.md) records this bounded choice.

Preserved intermediate failure: `jpeg-ring-1`, boot `0e95de451d730b06f0ad45e1e2c83aa9`, session **54169 terminal**. Four buffers retain all 1,800 frames but reverse queued delivery order; its device summary passes while independent camera and dependent JPEG assessments FAIL. All 30 JPEGs decode. Audio/IMU/UI and live/synthetic speech pass. Its initial `device-spectrum.json` used obsolete reference-1 and fails on the impulse peak; `device-spectrum-corrected.json` separately passes reference-2. Preserve both. Exact ring artifacts/manifests are alongside the FIFO candidate.

**Ownership issue identified at that checkpoint:** `.local/runs/20260921-camera/jpeg-lifecycle-review.md` records the pinned-driver queued-timeout risk. The current guard and controlled test above resolve unsafe error-path unwinding by failing closed, not cancellation/recovery. Device mode-cycle memory return and combined behavior remain open.

## Earlier failing JPEG checkpoint (retained)

`jpeg-baseline-1`, boot `efc223ac6c12b69d6a23e3460267c6dd`, session **33205 terminal**, remains FAIL. It delivered 1743 rows versus 1802 callbacks: 57 skipped sequence IDs across 32 gaps plus two completions after the final delivered frame. Its arithmetic `discarded_completed_at_stop=59` is not proof of stop-time discards. All 30 JPEGs decode and match hashes, but later sustained stages were skipped. This is not a preview-drop waiver.

Original firmware/artifacts remain under `.local/runs/20260920-baseline/jpeg-build-2-artifacts/` and `jpeg-build-manifest.json`, binary SHA-256 `6e5ed511639aa0762835b582ded6158d6d07412a36251e4cb8b27ee2c9cb8e8b`. Original capture/assessment and 98-test log are unchanged. That image was later superseded by owned preview and then the G-0002 trial image above.

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

Native camera acquisition:1280×720 RGB565 at~30fps, 60-second runs with observed backup-buffer starvation/completion accounting. Runtime rejects640×480. Camera receive is bounded; the final owned image is exported only after streaming stops. Camera+JPEG+owned live preview now passes with four buffers/FIFO for the recorded 60-second scope; network and full combined acceptance remain open.

Audio: repeated6000×480-frame48kHz baselines with raw immutability, separate16kHz speech and FFT2048 every2400frames; isolated read/consumer timing and driver counters pass. Live pairs retain141 block hashes/ranges each; independent derived-reference comparison passes. Synthetic speech has24pairs and FFT12fixtures. Current consumers are synchronous and retain copies, not raw pointers; future asynchronous ownership requires new evidence.

Physical microphone fixture is complete in `audio-ingress-1/microphone-position.json`: three near-USB/headphone-hole takes favor rawslot2; three farther-hole takes favor rawslot0, with modest margins/cross-pickup. User recognizes slots0/2 (0best) and no phrase in1/3. Keep physical-position names: factory MIC-L/R comments and annotated-photo naming disagree when combined. Earlier batch count mismatch is retained. Headphones reproduce0/2 in both ears at better level; speaker remains faint. Requested gain24dB is not hardware readback; no calibration claim.

ADRs0003–0009 are Active: pinned factory/IDF and BSP ownership, capture completion, radio lifecycle, immutable raw/owned speech, bounded camera FIFO, JPEG error-path fail-stop, and owned preview/render placement. Reserved0001/0002 were proposals, not revoked decisions. Do not mistake these bounded decisions for final combined architecture.
