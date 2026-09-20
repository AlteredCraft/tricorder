# 0002. Local instruments and a connected agent

Status: Proposed
Date: 2026-09-20

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

Use bounded commands such as request_capture, set_instrument_mode and cancel, with request IDs, deadlines, acknowledgements and device-side validation. A response references immutable capture IDs and their settings. Late responses from an earlier boot/session cannot change the active session. Acquisition never waits for an LLM response.

Propose separate audio paths:

- Measurement: retain pre-enhancement PCM and record physical channel mapping, sample rate, fixed gain, clipping and overruns.
- Conversation: derive a separate stream for resampling, VAD, AEC and noise suppression as needed.
- Alignment: retain sample counters and device timestamps; derive speech-processing delay from records.
- Playback: record speaker intervals. Keeping raw samples prevents software contamination but does not eliminate acoustic contamination from the device's own speaker.

Use a mocked agent before a live model to distinguish transport/device latency from inference latency. Consider WebRTC if measured continuous speech, interruption or media behavior warrants its complexity.

## Consequences

The Python side remains easy to inspect and evolve. The device can operate its instruments offline. We must design flow control, reconnect/cancel semantics, evidence identity and clock alignment. A local service is another component to run, and network/cloud round trips remain visible to the user.

No full-duplex or agent-latency claim is accepted yet. [G-0001.03](../plans/G-0001.03-audio-integrity.md) tests audio separation; [G-0001.04](../plans/G-0001.04-agent-interaction.md) tests interaction and recovery. Revise this proposal if WebSockets cannot meet the workload's timing/buffering needs, and record a controlled WebRTC comparison before switching.

Privacy-sensitive captures and provider keys remain outside the public repository. This is a data-handling requirement for the experiment artifacts, not a new approval step.
