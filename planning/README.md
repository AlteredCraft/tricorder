# Planning guidelines

We build features that the person holding the Tricorder can use, and let device trials decide what's true. Write the fewest words that let the next person or agent act.

Project conventions (runs, builds, device notes) live in [../CLAUDE.md](../CLAUDE.md).

## Shape

**Milestone → Feature → Trials.** ADRs record decisions and are not a level.

| Doc | Location | Holds | Words |
| --- | --- | --- | --- |
| Milestone | [milestones.md](milestones.md) ([template](milestone-template.md)) | Theme, features (link + status), Later list | ≤ 150 each |
| Feature | `features/F-NNNN-title.md` ([template](feature-template.md)) | Outcome, assumptions, trial log, next trial | ≤ 250 above the log; ≤ 80 per trial |
| ADR | `adrs/ADR-NNNN-title.md` ([template](adrs/ADR-template.md)) | A durable decision already made | ≤ 300 |
| Reference | `planning/<topic>.md` | Protocols and commands used by several features | ≤ 1,000 |

M-0001's goals and specs under `plans/` are closed history. Don't extend them.

**Size:** a feature fits in 1–3 days of real time. If it looks bigger, split it before starting. If it runs past 3 days, stop and split what's left.

## The trial loop

A trial is one build on the device, used by the user or driven by a script, with telemetry. Each session usually runs one loop.

1. **Plan** (the feature's Next): what we'll try, which assumption it tests, which telemetry answers it, and what the user does (minutes, place, whether it needs quiet, sound or battery).
2. **Build:** tests first for code. Add the events the trial needs in the same build (device monotonic time). Commit before flashing.
3. **Run:** record to `.local/runs/YYYYMMDD-topic/`.
4. **Analyze:** read the telemetry first. Confirm the trial completed in the logs, then ask the user what they saw and felt.
5. **Record:** one trial entry: what was tried, what the telemetry showed, what the user said, what we learned, and the decision (continue, adapt or stop).
6. **Adapt:** update Assumptions and Next. Change course when observations say so.

## Principles

- **Device first, then the Mac.** Every feature first works on the device alone. Talking to the Mac service (the agent, speech) extends it in a later trial.
- **Real use comes first.** Harden only what a trial shows is broken, or what a feature needs. Deferred work waits in the milestone's Later list.
- **Telemetry or it didn't happen.** Missing telemetry makes a trial inconclusive: fix the telemetry, don't guess.
- **Device numbers are baselines,** not invented targets.
- **The user's time is scarce.** State each trial's purpose and duration. Don't repeat a trial unless its code or conditions changed. Prefer script-driven trials for anything that doesn't need hands, ears or judgment.
- **Trial logs are append-only.** Correct with a new entry.

## Evidence

Runs are cited by directory name plus the commit SHA. Keep credentials and private data out of Git.

## Needs the user

Choosing or changing a feature's outcome, marking a feature Done or Dropped, and adding or closing a milestone. Everything else, proceed.

**Stopping mid-trial:** write a temporary `HANDOFF.md` at the repo root. The next session finishes that trial and deletes it.
