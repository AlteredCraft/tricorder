# Planning guidelines

We build features the person holding the Tricorder can use, and let using them decide what's true. Write the fewest words that let the next person or agent act. Project conventions (tests, runs, device notes) live in [../CLAUDE.md](../CLAUDE.md).

## Shape

**Milestone → Feature → Trials.** ADRs record decisions and are not a level.

| Doc | Location | Holds | Words |
| --- | --- | --- | --- |
| Milestone | [milestones.md](milestones.md) ([template](milestone-template.md)) | Theme, features (link + status), Later list | ≤ 150 each |
| Feature | `features/F-NNNN-title.md` ([template](feature-template.md)) | Outcome, next step, trial log | ≤ 150 above the log; a few lines per trial |
| ADR | `adrs/ADR-NNNN-title.md` ([template](adrs/ADR-template.md)) | A durable decision already made | ≤ 300 |
| Reference | `planning/<topic>.md` | Protocols and commands used by several features | ≤ 1,000 |

M-0001's goals and specs under `plans/` are closed history. Don't extend them.

**Size:** a feature fits in 1–3 days of real time. If it looks bigger, split it.

## Trials

A trial is one build on the device that the user tries. Build the whole feature when it is straightforward, including the Mac side; split into trials only when a step is uncertain.

1. **Build and flash.** Write the feature's **Next** as one or two lines: what the build does and what the user should try (minutes, place, quiet or sound, battery or USB).
2. **Try it.** The user uses it and says what happened. Logs help when something went wrong; they are not required for a result.
3. **Note it.** Add one trial entry: date, SHA, what was tried, what happened, what's next. Update **Next**.

## Principles

- **Real use comes first.** Harden only what a trial shows is broken, or what a feature needs. Deferred work waits in the milestone's Later list.
- **Good enough is done.** When the user says it works, move on. Don't repeat a trial unless its code or conditions changed, and don't re-run to get cleaner numbers.
- **Device numbers are baselines,** not invented targets.
- **The user's time is scarce.** Say what each trial is for and how long it takes. Prefer scripts and host runs for anything that doesn't need hands, ears or judgment.

## Needs the user

Choosing or changing a feature's outcome, marking a feature Done or Dropped, and adding or closing a milestone. Everything else, proceed.
