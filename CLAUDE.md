# Tricorder: agent notes

- Start with [HANDOFF.md](HANDOFF.md), then the active spec it names. Planning conventions and doc size budgets: [planning/README.md](planning/README.md).
- Keep milestone → goal → spec, ADRs and HANDOFF in sync, and keep them terse. Rewrite HANDOFF at the end of a session; don't append to it.
- Product progress (what the person holding the device sees and does) comes first. Hardening gates (G-0001) follow usefulness (G-0002).
- Don't ask the user for physical trials that replay, loopback or fault injection could cover. Say what a trial tests before asking.
- Commit before flashing a trial build. Don't create manifests, hash snapshots or red/green logs.
- Tests first for code changes: `.tools/investigation-env/bin/python -m unittest discover -s tests -q`. Build: `tools/idf.sh -C firmware build`.
- Opening the Tab5 serial port can reset it. Verify USB serial `E8:F6:0A:E2:E0:0E` before flashing.
- Never print or commit `.env.local.*` contents.
