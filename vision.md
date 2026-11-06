# Tricorder

**A handheld with a screen, touch and sensors, talking to an LLM that runs on the Mac beside it.**

Tricorder is an exploration project on the **M5Stack Tab5 (ESP32-P4)**. The device shows live readings from its sensors. The person uses touch and voice to say what they want to know. A text model, speech-to-text and text-to-speech on the Mac interpret the readings and answer. Nothing leaves the room: the device broadcasts its own Wi-Fi, the Mac joins it, and the models run locally (Ollama, Parakeet, Pocket TTS).

**Status:** in development. See the [milestones](planning/milestones.md) for what works today and what's next.

## The demo

1. Pick up the device. The start screen shows one tile per sensor, with a live reading where there is one.
2. Open **Sound**. Watch the live spectrum, make some noise, tap **Analysis**.
3. Tap **Voice note** and say what you heard or want to know. Tap **Explain**.
4. The Mac transcribes the note, the local model reads the analysis and answers, and the answer is shown on the device and spoken.

Every sensor gets the same shape: live instrument → analysis on the device → voice note → Explain.

## What we want to learn

- **The device:** what each built-in sensor can measure, how touch feels in the hand, what the screen can show, what it all costs in power.
- **The link:** the device's own Wi-Fi hotspot, round trips, uploads, spoken replies streamed back.
- **The model:** what a local 8B model can usefully say about sensor data, where it goes wrong, and what latency a person holding the device tolerates.

## Rules for the model

- Numbers come from the device or from the Mac's own computation. The model writes the explanation and must not invent measurements or claim a sensor it didn't get.
- Answers are short enough to speak. Observations stay separate from guesses.

## Dropped

Guided investigations (the Investigate tile, A/B comparisons with the agent steering; M-0001) worked but were not compelling to demo. Dropped 2026-11-05. The hotspot, service and speech path they built now carry Explain.

## Later

Camera to a local vision model. Motion and Power instruments with Explain. External sensors over the expansion ports. A hosted service instead of the Mac.

## Hardware references

- [M5Stack Tab5 documentation](https://docs.m5stack.com/en/core/Tab5)
- [M5Stack Tab5 factory demo source](https://github.com/m5stack/M5Tab5-UserDemo)

## License

[MIT](LICENSE)
