# Tricorder: agent notes

- Start with [planning/milestones.md](planning/milestones.md) and the active feature's **Next** trial. Planning rules and word limits: [planning/README.md](planning/README.md). Follow its **Needs the user** list; otherwise proceed.
- Scope each session to one trial loop: plan, build, run, analyze telemetry, get the user's feedback, record the trial and adapt Next. Keep features to 1–3 days of real time.
- Product progress (what the person holding the device sees and does) comes first. Harden only what a trial shows is broken, or what a feature needs.
- Tests first for code changes: `.tools/investigation-env/bin/python -m unittest discover -s tests -q`. Build: `tools/idf.sh -C firmware build`.
- Device gotchas (serial reset, USB identity, provisioning) are in [README.md](README.md#device-notes).

## Evidence

- Runs live in private `.local/runs/YYYYMMDD-topic/` (`manifest.json`, `events.jsonl`, `captures/`, `summary.json`). Cite them by directory name, plus the commit SHA.
- `tools/capture_serial.py` writes boot-scoped, sequence-numbered device events and hash-checked raw media; `summary.json` marks each named check pass/fail/inconclusive. Use device monotonic time for durations; don't subtract host and device clocks.
- **Commit before flashing a trial build.** The SHA identifies the build.

## Trials

- Every trial build logs the events that answer its question. Read them before asking the user, and confirm the trial completed in the logs first.
- Use host tests, SD replay and fault injection for code correctness. Device trials with the user are for what needs hands, ears or judgment: feel, usefulness, acoustics, power.
- Say where a trial can run (quiet, noisy, café, on battery). Guidance plays through headphones when plugged in; the speaker turns off.
- Things needing the user's hands or equipment go in [TODO.md](TODO.md). Device state (current Wi-Fi provisioning) goes in [README.md](README.md#device-notes), not TODO.
