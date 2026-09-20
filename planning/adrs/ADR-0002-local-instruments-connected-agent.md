# 0002. Local instruments and a connected agent

Status: Proposed
Date: 2026-09-20
Owner: Agent implementing G-0001.03–.04
Review trigger: First outcome recorded for G-0001.03; then each outcome or scope change in G-0001.04, including partial/refuted results
Revision: 2026-09-20 — align with the user's agreed direction: Python service on the Mac for early R&D, with a later hosted deployment using the same device/service boundary. Status remains Proposed pending experiment evidence.

## Context

A handheld investigation needs immediate feedback even when an agent is slow or disconnected. The agent must reference actual captures, and speech enhancement must not remove the signal under investigation.

## Options considered

1. **Local instruments with a Python service over WebSockets.** Simple, inspectable control and evidence protocol; application code owns media buffering and interruption.
2. **Local instruments with WebRTC media.** A candidate for continuous, interruptible conversation; adds signaling, codecs and media-session integration.
3. **Direct device-to-model integration.** Fewer service hops; more provider-specific session logic and credential lifecycle on the device.
4. **Entirely local reasoning.** Useful for bounded detection and commands; a general multimodal conversational agent on this hardware has not been established.

[FastAPI documents WebSockets](https://fastapi.tiangolo.com/advanced/websockets/). [Espressif's WebRTC solution](https://github.com/espressif/esp-webrtc-solution) provides capture, rendering and two-way-media examples. Their existence does not prove an unchanged Tab5 port or our latency targets. [ESP-SR](https://github.com/espressif/esp-sr) documents P4 speech-processing support.

## Decision

**Propose** local acquisition, measurement DSP, UI and immediate feedback, plus an asynchronous Python agent service, with FastAPI as an initial candidate. Evaluate WebSockets first. Keep model adapters replaceable; choose speech/model providers separately.

Start the service on the user's Mac, reached by the Tab5 over the local Wi-Fi network. Use a scripted mock agent first, then a live provider adapter. The service manages conversation context, assembles selected evidence for model requests, checks evidence references and coordinates model/speech services. Python is chosen for integration and experimentation; the service need not perform model inference itself.

Preserve a path to hosting this service later: use a configurable service address and a device-initiated connection, and keep the application protocol independent of the Mac and the model provider. Provider credentials stay on the service. A hosted deployment would remove the Mac dependency for conversation, while local instruments remain independent of service availability. Hosted deployment and its device authentication, encrypted transport, credential provisioning and capture-retention policy require a later spec; they are not part of the initial LAN experiment.

Use bounded commands such as request_capture, set_instrument_mode and cancel, with request IDs, deadlines, acknowledgements and device-side validation. A response references immutable capture IDs and their settings. Late responses from an earlier boot/session cannot change the active session. Acquisition never waits for an LLM response.

Propose separate audio paths:

- Measurement: retain pre-enhancement PCM and record physical channel mapping, sample rate, fixed gain, clipping and overruns.
- Conversation: derive a separate stream for resampling, VAD, AEC and noise suppression as needed.
- Alignment: retain sample counters and device timestamps; derive speech-processing delay from records.
- Playback: record speaker intervals. Keeping raw samples prevents software contamination but does not eliminate acoustic contamination from the device's own speaker.

Use a mocked agent before a live model to distinguish transport/device latency from inference latency. Consider WebRTC if measured continuous speech, interruption or media behavior warrants its complexity.

## Consequences

The Python side remains easy to inspect and evolve. The device can operate its instruments offline. We must design flow control, reconnect/cancel semantics, evidence identity and clock alignment. During local R&D, conversation depends on the Mac service being available, plus provider connectivity when using a remote model. Hosting adds operational work and internet variability; local measurements do not establish hosted latency or reliability.

No full-duplex or agent-latency claim is accepted yet. [G-0001.03](../plans/G-0001.03-audio-integrity.md) tests audio separation; [G-0001.04](../plans/G-0001.04-agent-interaction.md) tests interaction and recovery. Revise this proposal if WebSockets cannot meet the workload's timing/buffering needs, and record a controlled WebRTC comparison before switching.

Privacy-sensitive captures and provider keys remain outside the public repository. This is a data-handling requirement for the experiment artifacts, not a new approval step.

## Decision review

Acceptance conditions: The linked .03/.04 evidence must support separated measurement audio, responsive local instruments, correct evidence references, cancellation/recovery and usable interaction on the local deployment. Record the tested transport/provider configuration and its limits. Hosting, local inference and full-duplex speech are deferred capabilities, not acceptance gates for this decision.

- 2026-09-20: **Proposed.** Reviewed the user's agreement to a Mac service first and a later hosting path. The .03/.04 experiments are unbuilt, so no audio or interaction result supports technical acceptance yet. Next action: validate .03's audio separation after hardware bring-up; review here when its result is recorded, then after .04's mock and live-agent results. A transport failure requires a decision review and the controlled comparison described above, not indefinite Proposed status.
