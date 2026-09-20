# Tricorder

A handheld, agent-assisted instrument for exploring the physical world with the M5Stack Tab5 (ESP32-P4).

**This project is co-developed with OpenAI Codex.**

Hold it, point it, move it, and ask questions. The goal is to learn what the device can do while a person and an agent investigate something together in real time.

## Start here

- [Vision](vision.md) — the complete product concept, interaction loop, modes and hardware roles.
- [Planning guidelines](planning/README.md) — goals, hypothesis-driven specs and architecture decision records.
- [Milestones](planning/milestones.md) — Milestone → Goal → Spec, with links to architecture decisions and validation work.
- [Agent handoff](HANDOFF.md) — current state and how to continue locally.

## Status

Planning and research only. The agreed starting stack is C++/ESP-IDF with LVGL on the Tab5 and a Python agent service on the developer's Mac for early R&D, with a path to hosting the service later. Begin with a mock agent; model and speech providers remain undecided. No firmware, backend, test harness or hardware validation has been implemented. Candidate architectures and research live in the specs; ADRs will record architectural choices actually made from their evidence. Exact versions and peripheral drivers require validation on the actual device.

## License

[MIT](LICENSE)
