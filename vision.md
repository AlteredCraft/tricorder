# Tricorder

**A handheld instrument you and an agent operate together.**

Tricorder is an exploration project for the **M5Stack Tab5 IoT Development Kit (ESP32-P4)**. Hold it, point it, move it, and ask questions. The agent helps choose what to measure and interprets the evidence as you collect it.

The goal is to learn about both the physical world and the device itself by giving every built-in sensor a meaningful role.

> “I learned something about this object—and something about what my device can do.”

**Status:** in development. The experiences below describe intended behavior; see [HANDOFF.md](HANDOFF.md) for what works today and the [milestones](planning/milestones.md) for the plan.

## The experience

The Tab5 is a tactile device. Its screen, physical movement, sound, and camera should make it satisfying to use in your hands.

The primary experience is a person and an agent investigating something together in real time. Passive monitoring and unattended recording are outside the initial focus.

The core interaction is:

**Ask → measure → get feedback → adjust → discover.**

You bring curiosity, context, and physical control. The device brings measurements and immediate feedback. The agent suggests useful next steps, explains what the evidence supports, and helps decide what to try next.

Live instruments remain visible while the conversation happens. You can inspect readings, repeat a measurement, change direction, or disagree with the agent.

## An example: investigating a rattling desk fan

1. **Ask.** Hold the Tricorder near the fan and ask, “Can we figure out when this rattles?”
2. **Establish context.** Show the fan through the camera. The agent uses the image to understand the setup, without treating appearance as proof of a fault.
3. **Plan a comparison.** The agent asks for a few seconds of sound at each speed. You choose when to begin each capture.
4. **Measure.** Watch a live sound spectrum. Mark the moment you hear the rattle.
5. **Compare.** Examine the frequencies or repeating patterns that changed between captures.
6. **Adjust.** The agent suggests another measurement: “Move closer to the base and repeat.” The motion sensor can help indicate when the handheld device has settled.
7. **Discover.** Review an annotated comparison, a possible explanation, the evidence behind it, and what remains uncertain.

If the investigation calls for vibration measurements, the motion sensor needs an appropriate physical connection to the object. Holding the device nearby only measures the movement of the device itself.

The same interaction could help compare fan settings, investigate a desk rattle, explore resonant sounds, or find which position produces a clearer recording.

## Three complementary modes

| Mode | What you do | What the device and agent provide |
| --- | --- | --- |
| **Explore** | Open an instrument, move the device, and manipulate its controls. | Immediate readings, sound or visual feedback, and explanations of what the hardware measures. |
| **Investigate** | Ask a question and work through a series of measurements. | A guided experiment, contextual prompts, and interpretations tied to collected evidence. |
| **Compare** | Capture A and B, or compare a new reading with an earlier baseline. | Aligned observations, highlighted differences, and suggestions for a useful follow-up. |

These modes should work together. An investigation can open a live instrument, move into a comparison, and return to the conversation without losing context.

## Learn the whole device

We want to exercise all built-in sensors over time, while also exploring the inputs, outputs, communications, and storage that make them useful. A capability should earn its place in an interaction; every sensor does not need to run simultaneously.

| Capability | Intended role | What we want to learn |
| --- | --- | --- |
| **Camera** | Give the agent visual context; capture, select, and annotate visual evidence. | Image quality, framing, useful capture rates, and the cost of moving images through the system. |
| **Microphones** | Spoken interaction, live sound analysis, and comparison recordings. | Levels, clipping, noise, frequency content, channel behavior, and interaction with speaker playback. |
| **Accelerometer and gyroscope** | Device tilt, movement, vibration, steadiness guidance, and deliberate gesture controls. | Sampling, orientation, drift, mounting effects, and meaningful limits on measurement. |
| **Touchscreen** | Select a region, mark an event, tune a measurement, and compare results. | Readability, responsiveness, and controls that feel good while holding the device. |
| **Speaker and headphones** | Spoken guidance, playback, and audible feedback that changes with a measurement. | Latency, intelligibility, feedback loops, and when sound communicates better than a graph. |
| **Power monitoring** | Expose the device’s own electrical consumption as features activate. | The energy cost of camera, audio, display, processing, and wireless activity. |
| **Clock** | Timestamp and align observations. | Timing accuracy and synchronization across measurements. |
| **microSD storage** | Save observations, annotations, and comparison baselines for replay. | Storage throughput, session organization, and recovery from interruptions. |
| **Wi-Fi** | Connect the device to the agent and supporting computation. | Connection quality, round-trip latency, and graceful behavior when disconnected. |
| **USB and expansion interfaces** | Explore peripherals and introduce additional sensors later. | Compatibility, power requirements, and how new capabilities join the instrument interface. |
| **Sleep and wake controls** | Make the instrument ready when picked up and economical between interactions. | Wake behavior, startup delay, state restoration, and power tradeoffs. |

The built-in motion sensor measures the **device’s movement**. The power monitor measures the **device’s own electrical supply**. Environmental readings such as ambient temperature, humidity, and soil moisture require appropriate external sensors.

Geographic location needs another source; an accelerometer and gyroscope alone do not supply GPS position or absolute compass heading. Any internal temperature reading must be identified by its actual source and should not be presented as ambient temperature.

## A live capability diagram

The Tab5 factory demo screen is an important interface inspiration. It exposes components, connections, microphone tests, recording, motion readings, camera access, power use, peripheral scanning, and sleep/wake behavior.

Tricorder should carry forward that sense of visibility:

- Active camera, microphone, motion, and agent connections light up.
- Connections indicate how observations travel through the system.
- Tapping a component opens its readings, state, and relevant controls.
- Each instrument shows whether it is active, idle, unavailable, or disconnected.
- The user can see which evidence the agent is actually using.
- Power telemetry can reveal the cost of the currently active capabilities.

The diagram should provide an understandable view into the instrument, with deeper detail available on demand.

## The agent as an investigation partner

The agent should:

- Help turn a question into something the available hardware can measure.
- Explain why a proposed measurement would be useful.
- Guide framing, placement, duration, and repeatability.
- Give short, timely prompts while the user is holding the device.
- Refer to specific captures and readings when describing a result.
- Separate observations from hypotheses and express uncertainty.
- Suggest another comparison when the evidence is incomplete.
- Let the user interrupt, adjust, or take direct control.

The agent must not invent measurements or imply that an unavailable sensor supplied evidence. A plausible explanation of a sound is not a confirmed mechanical diagnosis.

## Responsive instruments and connected reasoning

The intended division of responsibility is straightforward: the device handles responsive acquisition, controls, live displays, and immediate feedback; a connected agent handles conversation and richer interpretation.

The agreed starting approach is C++/ESP-IDF with LVGL on the device and a Python service on the developer's Mac during early R&D. The service coordinates conversation, evidence and model/speech calls, beginning with a scripted mock agent. It can later move to a hosted web service that the Tab5 connects to directly, removing the Mac dependency. Running the Python service locally does not imply local model inference. Model/speech providers remain undecided; WebSockets and FastAPI are initial candidates to validate.

Core exploration should remain useful when the agent connection is unavailable. The interface should clearly distinguish live local readings from pending or unavailable agent responses.

## First milestone: one complete live investigation

Build one coherent interaction across **camera, microphone, motion, touch, and spoken feedback**:

1. Show an object.
2. Ask a question.
3. Collect a guided measurement.
4. See and hear immediate feedback.
5. Adjust the setup and capture a comparison.
6. Discuss the result with the agent.

Sound investigation is a promising first use: record a short sample, visualize it, repeat under a changed condition, and compare. Motion can support steadiness guidance, the camera can establish context, touch can mark events, and the speaker can provide prompts and playback.

The milestone is successful when the interaction is understandable, responsive, and useful on the actual handheld device. Hardware support and resource limits must be measured during implementation.

## Directions to preserve for later

- **Tricorder instruments:** sound, motion, and eventually environmental measurements, with “Compare with last time” as a shared capability.
- **Acoustic detective:** frequency exploration, short rolling captures, and investigation of intermittent sounds.
- **Teach by demonstration:** name a gesture or signal pattern, collect examples, and test whether the device can recognize it reliably.
- **Physical experiment studio:** connect an input, a rule, and an action on the touchscreen, with live values visible along each connection.
- **Living postcards:** combine a photograph, ambient sound, colors, and spoken context into an interactive memory.
- **Object memory:** identify an object and retrieve its earlier measurements, photographs, and notes during an active investigation.

These are possible extensions. The initial focus stays on a realtime, handheld Tricorder and learning the built-in capabilities.

## Hardware references

- [M5Stack Tab5 documentation](https://docs.m5stack.com/en/core/Tab5)
- [M5Stack Tab5 factory demo source](https://github.com/m5stack/M5Tab5-UserDemo)

Board and display revisions can differ. Confirm the actual unit and compatible drivers when choosing the stack.

## License

[MIT](LICENSE)
