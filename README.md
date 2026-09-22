# Tricorder

A handheld, agent-assisted instrument for exploring the physical world with the M5Stack Tab5 (ESP32-P4).

Hold it, point it, move it, and ask questions. The goal is to learn what the device can do while a person and an agent investigate something together in real time. Co-developed with OpenAI Codex and Claude Code.

## Start here

- [Vision](vision.md): the product concept.
- [Handoff](HANDOFF.md): current state, next steps, device setup.
- [Milestones](planning/milestones.md): Milestone → Goal → Spec, plus [ADRs](planning/adrs/).
- [Planning guidelines](planning/README.md): how the docs are kept.
- [Guided A/B protocol](planning/guided-ab-protocol.md): wire protocol and trial/replay commands.
- [TODO](TODO.md): tasks that need the operator.

## Layout

| Path | Contents |
| --- | --- |
| `firmware/` | ESP-IDF 5.4.2 app (`main/`): diagnostics, media owner, Guided A/B client, SD, Wi-Fi |
| `tools/` | Mac-side Python: serial collector, investigation service, provisioning, evidence assessors |
| `tests/` | Host tests (Python + native C++ under ASan) |
| `planning/` | Milestones, goals/specs, ADRs, fixtures |
| `.tools/`, `.local/` | Ignored: toolchains, private runs, captures, backups |

## Development

Requires Git, `uv` and Python 3.

```sh
python3 tools/bootstrap.py                     # pinned vendor sources + ESP32-P4 toolchain
tools/idf.sh -C firmware build
tools/idf.sh -C firmware -p PORT flash         # confirm the board's USB identity first
python3 -m venv .tools/investigation-env
.tools/investigation-env/bin/python -m pip install -r tools/investigation-requirements.txt -r tools/openai-requirements.txt
.tools/investigation-env/bin/python -m unittest discover -s tests -q
```

Serial capture of a diagnostic run (see `--help` for `--checks`, `--stop-file`, `--spec-id`):

```sh
.tools/python-env/bin/python -m tools.capture_serial --port PORT --output .local/runs/NEW --seconds 360 --reset
```

Evidence assessors (`python3 -m tools.<name> RUN_DIR`): `camera_baseline_evidence`, `audio_baseline_evidence`, `imu_baseline_evidence`, `ui_baseline_evidence`, `jpeg_evidence`, `preview_evidence`, `restart_evidence`, `device_spectrum`, `investigation_evidence`. `tools.inspect_capture` converts a capture to PNG/WAV.

## Live text provider

Put `OPENROUTER_API_KEY` in the ignored `.env.local.openrouter` (parsed literally, never sourced), then:

```sh
.tools/investigation-env/bin/python -m tools.investigation_service --host MAC_LAN_IP --port 8765 \
  --output .local/runs/NEW --provider openrouter --model openai/gpt-5.6-sol --env .env.local.openrouter
```

Only verified measurement summaries and fixture notes go to the provider. Raw recordings stay local.

## License

[MIT](LICENSE)
