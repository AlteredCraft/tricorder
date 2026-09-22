# G-0002.01 mock protocol checkpoint

2026-09-21. Experimental version 1 implements the shared host/device mock slice of
[G-0002.01](plans/G-0002.01-guided-ab-slice.md). Three settling-corrected developmental
A/B loops and controlled delay/cancellation/disconnect/recovery checks have scoped
evidence. The current trial session is closed and all host trial processes are
stopped. Live model/speech integration remains deferred by the user and is not built.
See the [current handoff](../HANDOFF.md) and the slice requirement disposition for
fixture/timing limits. [ADR-0010](adrs/ADR-0010-device-owned-ab-lan-experiment.md)
records the bounded mock architecture; no parent-goal acceptance is claimed.

## Run and verify

From the repository root, keep this Python environment separate from ESP-IDF:

```sh
python3 -m venv .tools/investigation-env
.tools/investigation-env/bin/python -m pip install -r tools/investigation-requirements.txt
.tools/investigation-env/bin/python -m unittest discover -s tests -q
.tools/investigation-env/bin/python -m tools.investigation_service --output .local/runs/ab-mock
```

The default endpoint is `ws://127.0.0.1:8765`. For a device trial, use
`--host <Mac-LAN-IP>` and configure that endpoint on the device. The prototype
has no authentication/TLS and belongs on the experiment LAN, as scoped by .04.
The device client is available under **Guided A/B** after initialization. Use `--delay-seconds 5` for the controlled
mock-delay experiment. Ctrl-C closes the listener and retains incomplete data.
No provider credentials are required; no captures are sent to a cloud service.

The two real WebSocket tests require this environment and permission to bind
localhost. The default Python suite skips them if `websockets` is absent. The
remaining tests use standard Python and the existing host C++ test toolchain.
Loopback tests upload synthetic PCM explicitly; they are not handheld runs.

## Speaker fixture

The operator selected **a speaker playing a steady sound** on 2026-09-21.
[Prepared fixture](fixtures/G-0002.01-speaker-distance.json): continuous 1000 Hz,
8 inches then 16 inches, fixed source level/orientation, three seconds of four-slot
48 kHz signed 16-bit little-endian raw audio, requested gain 24 dB, measurement
slot 0 (farther microphone hole, from the retained microphone-position fixture).
Only distance changes. RMS includes DC and is expressed in raw digital counts
and dBFS; the B/A ratio is digital dB, not calibrated acoustic SPL.

Before the first acceptance run, record the speaker/signal source, exact fixed
output-level setting, room/background, and placement method. Freeze that setup
and this fixture together in the private run evidence. The JSON is a prepared
configuration, not a claim that this physical setup has already been verified.
Check that the chosen level neither clips nor disappears into the background;
retain/repeat any unsuitable trial. Stop moving before each capture. The
Tricorder speaker must be silent during both measurement windows; camera/IMU
are outside this workload. The implemented flow uses sequential capture then upload;
full concurrent sensor operation remains unmeasured.

## States and identity

Device reference sequence:

`idle → ready_a → recording_a → waiting → adjust → ready_b → recording_b → waiting → complete`

Cancel enters `cancelled` immediately; a late capture/reply cannot advance it.
A disconnect enters `offline`; expiry enters `incomplete`. None automatically
restarts a capture. A reconnect requires a fresh session ID. The UI must expose
these states and perform cancel locally before sending a network message.
`Investigation` in `tools/investigation.py` exercises that reference contract;
the C++ `InvestigationProtocol` enforces it independently and also waits for
the service acknowledgement before enabling adjustment/completion.

Every control message carries `version: 1`, `type`, `boot_id`, `session_id`.
IDs are 1–96 ASCII alphanumeric/underscore/hyphen characters. The service
requires a fresh exclusive `<boot_id>-<session_id>` directory, even after a
service restart. Responses echo request IDs and device deadlines exactly.
Mac monotonic receipt times and device times are different clock domains.

## Wire sequence

WebSocket text JSON only; duplicate keys, non-finite literals, unknown message
types/fields, binary messages and messages exceeding 32 KiB are rejected.

1. `hello` includes `fixture` matching the prepared JSON fields. The service
   freezes it in `manifest.json`, then returns `ready` and the provider name.
   This initial preset/text question bootstraps the mock only.
2. The device explicitly starts A locally, then uploads `capture_start` with
   `metadata`. The service returns `capture_ack` with `stage: "start"`.
3. Send ordered `capture_chunk` messages (`capture_id`, integer `offset`, base64
   `data`, at most 4096 decoded bytes). Chunks have no individual reply.
4. Send `capture_end` with `capture_id` and `sha256`. The service checks size,
   digest, settings, device integrity and speaker-inactive declarations, then
   returns `capture_ack`, `stage: "complete"`, and the hash. It preserves the
   existing `CaptureStore` start/chunk/end completion and partial-retention rules.
5. `turn` includes `request_id`, ordered `capture_ids: [A]`, `device_ms` and
   `deadline_ms` (1–60000 ms after `device_ms`). The service re-reads/verifies the
   saved bytes and computes measurements; it never accepts client-supplied RMS.
6. `guidance` includes matching version/boot/session/request/deadline,
   `capture_ids`, ordered `measurements`, `comparison: null`, and visible `text`.
   The device validates the full identity, known captures and deadline before
   applying it, and sends `ack` with `request_id`. The service responds
   `acknowledged`, `state: "adjust"`.
7. The operator adjusts the placement, confirms the actual adjustment on the
   device, and explicitly captures B. Repeat upload steps 2–4 with a distinct
   ID, identical settings and a later, nonoverlapping device acquisition window.
8. A second `turn` cites `[A, B]` and includes the operator's `adjustment` text.
   `comparison` returns both measurements and a structured comparison:
   `rms_delta_db = 20 log10(RMS_B/RMS_A)`, status and unit. Clipping or zero RMS
   makes the ratio `null` and status `inconclusive`. The device acknowledges it;
   service state becomes `complete`. No third capture/turn is allowed.

Capture metadata requires `boot_id`, `session_id`, `capture_id`, `format:
"pcm_s16le"`, `sample_rate_hz`, `channels`, `frames`, `gain_db` (requested, not
readback), `source_slot`, `physical_slot`, `size_bytes`, `acquisition_start_us`,
`acquisition_end_us`, `driver_epoch_integrity: true`, and
`speaker_active: false`. The receiver assigns completion status and final hash.
Retain firmware ingress proofs in the metadata when the device is integrated;
a source declaration alone does not independently establish acquisition quality.

`cancel` has no extra fields. It invalidates the pending result, cancels the
mock-delay task, retains partials, and returns `cancelled`. The device does not
wait for this acknowledgement to stop locally. Only one response may await an
acknowledgement. Unknown/stale/duplicate requests or acknowledgements cannot
create another capture or replace a result. A wire violation closes the socket
with a fixed sanitized reason and records the session as incomplete.

The Mac uses the supplied deadline **duration** to bound its own response work;
network transit time is still included in the device's final deadline check.
There is no clock synchronization assumption. A silent connection closes after
30 seconds; transport ping/pong is separate. Response send waits are bounded to
two seconds. The service's state labels describe receipt/processing, not the
physical start time of a device recording.

## Bounds, evidence and provider seam

One active connection, one active transfer, one pending provider response, two
captures/session. Each raw capture is at most 1,152,000 bytes, and total retained
raw data (including failed transfers) is reserved against 2,304,000 bytes/session.
The control budget is 640 incoming messages: two full captures at 4096-byte
chunks fit. Smaller chunks can intentionally exhaust it and fail the run.

The WebSocket receive high-water mark is four frames; max message size is 32 KiB,
compression is disabled, and the write high-water mark is 32 KiB. These use the
[pinned library's server controls](https://websockets.readthedocs.io/en/stable/reference/asyncio/server.html).
The archive allows 256 transcript events at at most 32 KiB/event and the server
allows at most 32 retained session directories under its output root. Capacity
exhaustion rejects work; it never deletes evidence. Use a new output root for a
new experiment batch, with deliberate retention management.

`manifest.json` records spec ID/revision, protocol, fixture, intended workload,
clock domains and bounds. `transcript.jsonl` retains sanitized control messages,
operator adjustment, acknowledgements, responses and closure status. Raw chunks
are stored in `captures/` and omitted from transcripts. Partial files remain
incomplete. Reusing a run or capture identity is rejected. This is bounded Mac
retention, not SD power-loss durability or G-0001 recovery acceptance.

`MockProvider` and future adapters must pass `validate_reply`: exact capture
joins, host-computed structured measurements/comparison, bounded text and no
extra command types. Free-text semantic correctness still requires transcript
and operator review. The asynchronous provider boundary is
`MockSession.provider_reply`; a future adapter must await network work there,
never block the event loop with a synchronous model call. Keys stay on the Mac.

The serial collector now accepts `--spec-id`, `--spec-revision`, and `--workload`.
An explicit nondefault spec requires both revision and workload. Legacy .01
commands still work and record unspecified fields as null, rather than inventing
historical revision/workload details. For slice collection use:

```sh
python3 -m tools.capture_serial --port <rediscovered-port> --output <new-private-run> \
  --spec-id G-0002.01 --spec-revision 2026-09-21 \
  --workload 'speaker distance A/B; explicit-turn audio; camera/IMU/playback inactive'
```

Rediscover USB identity before opening a port, and prefix real collectors with
`/usr/bin/caffeinate -is` per HANDOFF.md. No collector or hardware test is needed
to run the host tests above.

## Remaining integration

The device mock is built, flashed and physically exercised. Preserve the three
corrected developmental loops, controlled failure/recovery evidence and original
failures. Formal fixture notes and actual panel/pending-turn cancellation timing
still have the limits documented in the slice. Live spoken input/guidance, provider
selection/credentials and three operator-rated live loops remain required but
explicitly deferred. G-0002 and G-0001 remain incomplete.


## Device integration checkpoint — 2026-09-21

The existing media-owner task runs the A/B flow. LVGL callbacks enqueue one
operator action; Cancel sets an atomic flag and updates the visible state
locally before network cleanup. The worker checks cancel again after blocking
reads and before accepting replies. Captures never start from a remote message.
A fresh random session is required after completion, cancel, offline or expiry.

One 1,152,000-byte raw PCM buffer is allocated in PSRAM for a capture. RX is
closed before JSON generation/upload. Per-block ingress hashes, read timestamps,
exact frame coverage and before/after driver counters accompany each capture;
the service independently verifies these against retained bytes. One buffer is
released after its matching hash/completion acknowledgement, before B is captured.
The device retains at most two metadata/measurement snapshots and compares the
service's structured results with its own raw slot-0 RMS/peak/clipping values.
Legacy synthetic tests without ingress proofs remain explicitly synthetic.

The pinned IDF `tcp_transport` WebSocket layer connects to a RAM-only
`ws://host:port/path` endpoint. No new dependency, TLS, authentication, provider
key or automatic reconnect is introduced. IPv6, query strings and endpoint
credentials are unsupported in this LAN experiment. Incoming text is capped at
32 KiB; split reads/continuations are assembled in one fixed buffer. Binary,
wrong-state, stale, duplicate and unbacked replies fail closed. Control frames
are handled by IDF. Individual connect/send/read bounds are 3/2/1 seconds;
visible cancel does not wait for those operations. Partial-header read behavior
and DNS timing still need hardware failure evidence; these are not .04 latency
claims. Upload has a 30-second total budget, individual capture ACKs 5 seconds,
and inference plus acknowledgement 15 seconds. The host's existing 30-second
application idle limit also applies while the operator is positioning the unit.

`CONFIG_TRICORDER_GUIDED_AB_STARTUP=y` skips automatic camera/audio/DSP/baseline
stages for manual trials. It is off by default; the private trial sdkconfig and
binary are archived together. Startup identity/display/RTC/storage/radio checks
still run. The current prepared speaker fixture is embedded directly by CMake
from its JSON source, avoiding a second handwritten fixture in firmware.

Setup: join Wi-Fi, open **Guided A/B**, enter the Mac endpoint and choose
**Start mock**. At 8 inches choose **Record A**; after guidance move to 16 inches and
choose **Confirm position B**, then **Record B**. The confirmation records the preset
actual-adjustment assertion; do not confirm it if the source/settings or placement
differ. Read the comparison on the scrollable transcript. Cancel/Back and a fresh
Start are available for subsequent sessions. This remains preset/text-only mock
bootstrap; spoken ask/guidance and live-provider usefulness are not implemented.

Current checkpoint: 172 host tests pass, including ASan C++ state, framing and
capture-owner tests and two real localhost WebSocket tests. P4 compilation and
trial startup pass. Logs, exact firmware sources/config/binary and retained trial
evidence are under `.local/runs/20260921-g0002-device/`; no physical A/B pass is
claimed by these software/startup results.


2026-09-21 fixture revision: the user requested imperial measurements and 30%
MacBook system volume going forward. Use 8-inch/16-inch positions from a fixed
speaker reference to the farther microphone hole. This supersedes the prepared
20/40 cm configuration (no A/B captures were taken with it). Device question,
placements and recorded adjustment now come from the embedded shared fixture.
The optional `CONFIG_TRICORDER_INVESTIGATION_ENDPOINT` sets an editable initial
address; the trial uses a private sdkconfig. The keyboard now uses explicit
top-left anchoring, with its resolved bounds checked at startup.


## Settling prefix and independent assessment

The first real loop retained valid bytes but produced a misleading steady-tone
comparison because codec-startup transients dominated both recordings. The tested correction
drains 24,000 frames (0.5 seconds) before the three-second retained raw
window, without restarting RX at the boundary. `warmup_frames: 24000` and
`epoch_start_us` declare this prefix. Driver before/after counters cover
1,344,000 bytes (prefix plus the 1,152,000 retained raw bytes); ingress block
hashes/timestamps cover only the retained three seconds. Old raw data is preserved.

`python -m tools.investigation_evidence <session-directory>` independently
recomputes slot measurements, source/ingress hashes, driver extents, settings,
A/B order and transcript request/reply/ACK joins. A passing technical assessment
does not establish physical stationarity or usefulness, as the first retained
failure demonstrates. Local cancel now retains request and media-owner-stop
monotonic timestamps; neither is a claim about actual panel submission timing.


2026-09-21 final mock closeout: three settling-enabled loops have verified raw
windows and no original startup spikes, with B/A −6.9860, −7.5752 and −9.9557
digital dB. The user confirmed measured 8/16-inch distances and no noticeable
background noise for the two resumed repeats. Five-second replies, pending-turn
cancellation and fresh recording/guidance after a controlled outage are recorded.
Capture cancellation stopped its owner in 15.921 ms; pending-turn device timing
and actual panel latency remain unmeasured. Serial attachment errors and original
FAIL summaries are retained separately from scoped parsed-event assessments.
All trial processes are stopped, 172 tests pass, and trial-4 artifacts remain
unchanged. Live-provider/speech/usefulness work remains deferred; see the handoff
for the evidence index and precise acceptance limitations.


## SD-assisted testing — 2026-09-22

The diagnostic now mounts the supplied microSD card without formatting it. USB
provisioning saves the Wi-Fi name/password and optional Mac endpoint under
`/sdcard/tricorder/`. On the next ordinary boot, it loads those settings and joins
Wi-Fi; the software-reset acceptance fixture still does not auto-join. Manual
Wi-Fi UI edits remain temporary. The SD card contains plaintext credentials;
keep it private. Neither the firmware binary nor Git contains those credentials.

Rediscover the verified Tab5 USB identity, stop any serial collector using that
port, then provision from a local environment file (both `WIFI_NAME` and
`WIFI_SSID` are accepted, along with `WIFI_PASSWORD`). This workspace's supplied
file is `env.local.northbank`, without a leading dot. Values are parsed literally,
without shell expansion. Use the Mac's current LAN address for the endpoint:

```sh
/usr/bin/caffeinate -is .tools/python-env/bin/python -m tools.provision_device \
  --env env.local.northbank --port /dev/cu.usbmodem1101 \
  --endpoint ws://MAC_LAN_IP:8765/ --output .local/runs/NEW-provision
```

The tool verifies USB serial `E8:F6:0A:E2:E0:0E`, sends credentials through the
bounded USB command reader, and records only selected non-secret status events.
It requires both a successful save and a subsequent IP event. A save may succeed
while association fails; its timeout must not be called a connected result.
Reprovisioning can update settings: a verified staged file replaces the current
configuration, with a previous valid file retained for boot fallback. Staged
files are never boot configuration. Host tests cover interrupted rename states;
physical power-loss durability has not been established.

Each completed A/B recording is saved before upload to
`/sdcard/tricorder/captures/<capture_id>.raw` and `.json`. The original metadata
contains SHA-256, ingress block proofs, boot/session identity and acquisition
timestamps. Writes use exclusive `.part` files, sync and exact readback; metadata
is published last. A raw file without metadata is incomplete. Existing capture
files are never overwritten or automatically deleted. SD failure is visible and
logged; the existing verified LAN upload remains usable without SD. Acquisition
still starts only through the local Record button. No sensor runs during the
storage self-test; its 1,152,000 bytes are labeled `synthetic_storage_test` and
must never be treated as an acoustic recording.

Between trials, download and independently verify public capture files:

```sh
.tools/investigation-env/bin/python -m tools.download_storage \
  --url http://DEVICE_IP --output .local/runs/NEW-sd-download
```

`/test-files` lists at most 128 public names and explicitly reports truncation.
`/test-file/<basename>` permits only capture `.raw`/`.json` files, excluding
credentials, path traversal and partial files. The downloader rejects mismatched
identities, lengths and SHA-256, and reports orphaned raw files or truncated
listings as incomplete. Download between trials: bulk serving shares the small
HTTP server with echo probes, so simultaneous transfer is not an echo-latency
acceptance fixture. This remains a trusted-LAN development service.

G-0002 remains in progress. SD persistence/byte integrity does not establish a
new physical A/B loop, recovery from power loss during an SD write, live model or
speech integration, or combined-workload acceptance.

Measured storage cost on this card is approximately 3.01 seconds for write plus
readback of a 1,152,000-byte raw capture. This is extra post-acquisition time,
not improved audio or agent latency. The gain is avoiding repeated setup and
retaining evidence independently of the Mac upload.
## Replaying an archived A/B pair

Use replay to test transfer/guidance with an existing committed pair. It never
starts the microphone or writes replacement capture files. Original identities,
acquisition timestamps, hashes and ingress proofs stay unchanged. The server
must explicitly accept replay; normal mock mode rejects it. Replays are not new
physical A/B trials and cannot repair a failed original transcript.

Start a fresh private output directory on the Mac's specific test LAN address:

```sh
.tools/investigation-env/bin/python -m tools.investigation_service \
  --host MAC_LAN_IP --port 8765 --output .local/runs/replay-NEW/mock --replay-only
```

With the saved endpoint pointing there, use one serial owner to reset, collect
startup evidence and send the fixed USB replay command after SD/network readiness:

```sh
/usr/bin/caffeinate -is .tools/python-env/bin/python -m tools.capture_serial \
  --port /dev/cu.usbmodem1101 --output .local/runs/replay-NEW/serial \
  --seconds 90 --reset --replay-session ab-EXACT_32_LOWERCASE_HEX \
  --checks sd_roundtrip wifi_initialize storage_http \
  --spec-id G-0002.01 --spec-revision 2026-09-22 \
  --workload 'SD transport replay; no new sensor acquisition'
```

Match the USB identity before using that example port. The command loads
`SESSION-a` and `SESSION-b`; missing, corrupt or mismatched files fail closed.
Cancel still works locally. The UI and server manifest mark the replay explicitly.
Assess the saved mock session with `tools.investigation_evidence`, then compare
both received raw files and original metadata with the downloaded SD pair.
The collector's summary alone does not establish content/protocol correctness.
Stop the listener after the bounded trial. Numeric `investigation_transport`
events include requested/sent byte counts, errno and elapsed send time, never
payloads or credentials.
