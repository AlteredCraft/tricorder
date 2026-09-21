# G-0002.01 mock protocol checkpoint

2026-09-21. Experimental version 1, implementing the first host-side slice of
[G-0002.01](plans/G-0002.01-guided-ab-slice.md). Firmware transport/UI and live
speech/provider integration are not built. The host state reducer is a reference
for those device checks; passing it does not measure handheld responsiveness.
No new architecture ADR or acceptance result is claimed.

## Run and verify

From the repository root, keep this Python environment separate from ESP-IDF:

```sh
python3 -m venv .tools/investigation-env
.tools/investigation-env/bin/python -m pip install -r tools/investigation-requirements.txt
.tools/investigation-env/bin/python -m unittest discover -s tests -q
.tools/investigation-env/bin/python -m tools.investigation_service --output .local/runs/ab-mock
```

The default endpoint is `ws://127.0.0.1:8765`. For a future device trial, use
`--host <Mac-LAN-IP>` and configure that endpoint on the device. The prototype
has no authentication/TLS and belongs on the experiment LAN, as scoped by .04.
The device client does not exist yet. Use `--delay-seconds 5` for the controlled
mock-delay experiment. Ctrl-C closes the listener and retains incomplete data.
No provider credentials are required; no captures are sent to a cloud service.

The two real WebSocket tests require this environment and permission to bind
localhost. The default Python suite skips them if `websockets` is absent. The
remaining tests use standard Python and the existing host C++ test toolchain.
Loopback tests upload synthetic PCM explicitly; they are not handheld runs.

## Speaker fixture

The operator selected **a speaker playing a steady sound** on 2026-09-21.
[Prepared fixture](fixtures/G-0002.01-speaker-distance.json): continuous 1000 Hz,
20 cm then 40 cm, fixed source level/orientation, three seconds of four-slot
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
are outside this initial workload. Actual on-device overlap remains unmeasured.

## States and identity

Device reference sequence:

`idle → ready_a → recording_a → waiting → adjust → ready_b → recording_b → waiting → complete`

Cancel enters `cancelled` immediately; a late capture/reply cannot advance it.
A disconnect enters `offline`; expiry enters `incomplete`. None automatically
restarts a capture. A reconnect requires a fresh session ID. The UI must expose
these states and perform cancel locally before sending a network message.
`Investigation` in `tools/investigation.py` exercises that reference contract;
the future C++ device reducer must enforce it independently.

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

Implement the C++ state/deadline/identity guard with tests, a configurable
device-initiated WebSocket client, and on-device controls that preserve the
existing codec owner and immutable raw capture boundary. Integrate capture
completion without delaying cancel or including playback in measurement windows.
Then build/flash and record the three real mock loops and delay/cancel/reconnect
trials. Live spoken input/guidance, provider selection/credentials and three
operator-rated live loops remain required. G-0002 and G-0001 are both incomplete.
