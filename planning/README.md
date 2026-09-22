# Planning guidelines

Planning docs exist so the next person (or agent) can pick up the work quickly. Write the fewest words that let them act. State results plainly. Mention open work only as a next action.

## Principles

- **One home per fact.** Link to it from elsewhere instead of repeating it.
- **Git and `.local/runs/` are the archive.** Docs hold current state plus one-line results. Don't carry history forward in prose; `git log` has it.
- **Keep within the size budgets below.** When a doc goes over, prune or summarize before adding more.
- **Failures get one line:** what failed, why, what fixed it, evidence path. The run directory preserves the details.
- **Missing data is inconclusive, not a pass.** Say so once, in the relevant check.

## Hierarchy

**Milestone → Goal → Spec.** Each goal has one parent milestone and each spec one parent goal. ADRs are linked decision records, not a level in the hierarchy.

| Doc | Location | Contents | Budget |
| --- | --- | --- | --- |
| Milestone | [milestones.md](milestones.md) | Scope, deliverable, done-when, goal table with one-line status | ≤ 40 lines each |
| Goal | `plans/G-NNNN-title.md` ([template](goal-template.md)) | Outcome, measure, spec table, status | ≤ 30 lines |
| Spec | `plans/G-NNNN.nn-title.md` ([template](spec-template.md)) | Hypothesis, refuted-if, checks, observed | Proposal ≤ 40 lines; Observed ≤ 2 lines per entry |
| ADR | `adrs/ADR-NNNN-title.md` ([template](adrs/ADR-template.md)) | A durable choice already made, with evidence | ≤ 30 lines |
| Handoff | [../HANDOFF.md](../HANDOFF.md) | State, next steps, device/env gotchas, commands | ≤ 80 lines; rewrite it, don't append |
| Operator TODO | [../TODO.md](../TODO.md) | Only things needing the user's hands or equipment | Short list |

Reference material that several specs use (e.g. [guided-ab-protocol.md](guided-ab-protocol.md)) may live in `planning/`. Keep it operational: the protocol, commands and limits.

Status values: goals and milestones use Not started, In progress, Met or Partly met. Specs use Proposed, In progress, Confirmed, Refuted, Partial or Not built. A spec's result doesn't automatically set its goal's status; assess the goal's outcome directly.

## Specs

- **Checks** are concrete and numeric where possible: evidence source plus pass condition.
- **Observed** is a bullet list: `- YYYY-MM-DD — result (key numbers). Evidence: run-dir. → ADR-NNNN`. End with one `- Open:` bullet listing what remains.
- Record measured results, bugs found and fixed, and decisions. Don't record: "checks written before implementation", plans, restated open gates, "no ADR needed", process/PID status, pauses.
- **Changing checks:** edit them and add a dated one-line `Revision:` to the header (what changed, why). Earlier results stand under the criteria they were measured against.

## ADRs

Record one when a choice becomes a constraint future work must honor: component boundary, resource ownership, concurrency model, transport contract, evidence format or trust boundary. Not for bug fixes, settings or UI tweaks. An ADR is born Active and states the decision, the alternatives in one line each, and its consequences.

**Revoking:** set `Status: Revoked by ADR-NNNN (YYYY-MM-DD): reason` (or `Revoked (date): reason; open in spec X`), keep the file, and update inbound links.

## Evidence

- Runs live in the private `.local/runs/YYYYMMDD-topic/` directories (`manifest.json`, `events.jsonl`, `captures/`, `summary.json`). Cite them by directory name.
- **Commit before flashing a build for a trial.** The git SHA identifies the build, so there's no need for source/hash manifests or artifact snapshots.
- Don't keep red/green test logs. The test suite and git history cover it.
- Keep credentials and private captures out of Git.

## Operator time

The user's physical time is the scarcest resource.

- Test transport, service and state-machine changes with host tests, SD replay, loopback and fault injection first. Ask for a physical trial only for what automation can't test: acoustics, touch/feel, usefulness, power, cold starts.
- Before asking, state in one sentence what the trial tests and which outcome would change the plan.
- Don't repeat a physical fixture unless the code or conditions it tests have changed.

## Agent workflow

1. **Start:** read [HANDOFF.md](../HANDOFF.md) and the active spec.
2. **Work:** write tests first for code changes. When a result lands, add its Observed bullet. When a durable choice is made, write the ADR in the same change.
3. **End:** rewrite HANDOFF.md. Update goal/milestone status lines only if they changed. Check the size budgets.
4. Ask the user when a trade-off changes product intent or scope.
