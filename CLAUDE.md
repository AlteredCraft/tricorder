# Tricorder: agent notes

- Start with [planning/milestones.md](planning/milestones.md) and the active spec's ordered `Open` list. Planning rules, statuses and word limits: [planning/README.md](planning/README.md). Follow its **Needs the user** list; otherwise proceed.
- Scope each session to one Open item: code, tests, the spec's Observed/verdict/Open update and any ADR, all together.
- Product progress (what the person holding the device sees and does) comes first. Hardening gates (G-0001) follow usefulness (G-0002).
- Tests first for code changes: `.tools/investigation-env/bin/python -m unittest discover -s tests -q`. Build: `tools/idf.sh -C firmware build`.
- Device gotchas (serial reset, USB identity, provisioning) are in [README.md](README.md#device-notes).

## Evidence

- Runs live in private `.local/runs/YYYYMMDD-topic/` (`manifest.json`, `events.jsonl`, `captures/`, `summary.json`). Cite them by directory name, plus the commit SHA.
- `tools/capture_serial.py` writes boot-scoped, sequence-numbered device events and hash-checked raw media; `summary.json` marks each named check pass/fail/inconclusive. Use device monotonic time for durations; don't subtract host and device clocks.
- **Commit before flashing a trial build.** The SHA identifies the build.

## Physical trials

- Test transport, service and state-machine changes with host tests, SD replay, loopback and fault injection first. Physical trials are for acoustics, touch/feel, usefulness, power and cold starts.
- Things needing the user's hands or equipment go in [TODO.md](TODO.md). Device state (current Wi-Fi provisioning) goes in [README.md](README.md#device-notes), not TODO.
