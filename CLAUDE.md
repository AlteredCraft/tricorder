# Tricorder: agent notes

- Start with [planning/milestones.md](planning/milestones.md) and the active spec's ordered `Open` list. Conventions and size budgets: [planning/README.md](planning/README.md).
- Scope each session to finish one Open item: code, tests, the spec's Observed/Open update and any ADR, all together. If a session has to stop mid-item, write a temporary `HANDOFF.md`; the next session finishes that item and deletes the file.
- Keep milestone → goal → spec and ADRs in sync and terse.
- Product progress (what the person holding the device sees and does) comes first. Hardening gates (G-0001) follow usefulness (G-0002).
- Don't ask the user for physical trials that replay, loopback or fault injection could cover. Say what a trial tests before asking.
- Commit before flashing a trial build. Don't create manifests, hash snapshots or red/green logs.
- Tests first for code changes: `.tools/investigation-env/bin/python -m unittest discover -s tests -q`. Build: `tools/idf.sh -C firmware build`.
- Device gotchas (serial reset, USB identity, provisioning) are in [README.md](README.md#device-notes).
