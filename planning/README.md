# Planning guidelines

Planning docs let the next person or agent pick up the work and show, at any level, what is done. Write the fewest words that let a reader act.

Project-specific conventions (evidence locations, build/trial rules, operator tasks) live in [../AGENTS.md](../AGENTS.md), not here.

## Principles

- **One home per fact.** Each fact has one authoritative file (table below). Elsewhere, link to it.
- **Specs test hypotheses. Git holds the work.** Planning docs record what was expected, what was observed, and the commit or PR behind it.
- **Logs are append-only.** Never rewrite a dated Observed entry. Mark stale entries `~~like this~~ (superseded YYYY-MM-DD)` and add a new one.
- **Stay within the word limits.** Check with `wc -w` at session end. Over a limit means the doc is doing too much: split it, don't trim evidence.
- **Missing data is inconclusive, not a pass.**

## Hierarchy and homes

**Milestone → Goal → Spec.** A child names its one parent in its header, and the parent lists its children by link. ADRs are decision records, not a level.

| Doc | Location | Authoritative for | Words |
| --- | --- | --- | --- |
| Milestone | [milestones.md](milestones.md) ([template](milestone-template.md)) | Scope, done-when, active-spec pointer | ≤ 250 each |
| Goal | `plans/G-NNNN-title.md` ([template](goal-template.md)) | Outcome, measure, goal result | ≤ 150 |
| Spec | `plans/G-NNNN.nn-title.md` ([template](spec-template.md)) | Hypothesis, checks and verdicts, observations, next work | ≤ 300 above Observed; ≤ 50 per entry |
| ADR | `adrs/ADR-NNNN-title.md` ([template](adrs/ADR-template.md)) | A durable decision already made | ≤ 300 |
| Reference | `planning/<topic>.md` | Protocols, commands, limits used by several specs | ≤ 1,000 |
| Open decision | GitHub issue | A choice not yet made | n/a |

Parent tables hold **link + status only**. The child's header is authoritative; the parent's column mirrors it in the same change.

## Status and completion

**Spec**, set from evidence:

- `Proposed`: no work started. `In progress`: work started.
- `Confirmed`: every check is `[pass]`.
- `Refuted`: a Refuted-if condition was observed. Cite the entry.
- `Partial`: closed with checks still open, after the user approves. The open checks move to a linked successor spec.

Confirmed, Refuted and Partial are closed. A closed spec only gains strike-throughs and a successor link.

**Goal:** `Not started`, `In progress`, `Met` or `Dropped` (with reason). Met when all its specs are closed and the Measure is satisfied, recorded as a dated one-line **Result** citing evidence. Spec results don't set it automatically.

**Milestone:** `Not started`, `In progress` or `Done`. Done when every goal is Met. Never closed partly done: move unmet work to another milestone, record the move, then close.

## Specs

- **Checks** are numbered, concrete and numeric where possible: evidence source → pass condition. Each check starts with a verdict: `[open]`, `[pass]` or `[fail]`. The Observed entry tagged `C<n>` is its evidence.
- **Build** (optional) is a few one-line steps, and each step serves a check. If new work isn't validated by any check, add a check (Revision) or open a new spec.
- **Observed** is the append-only log: `- YYYY-MM-DD — [C2 pass] result (key numbers). Evidence: <ref> · <commit or PR>. → ADR-NNNN`. Every entry cites a commit SHA or PR. Record results, bugs fixed and decisions; not plans or process chatter.
- **Open** is the ordered next work. Each item fits in one session. It's current state, edited freely. Items waiting on a decision link the GitHub issue.
- **Changing checks:** add a dated `Revision:` line in the header. You can add or tighten a check freely. Loosening or removing one needs the user, noted `(user-approved)`. Earlier results stand under their original criteria. A changed check reverts to `[open]` unless existing evidence meets it.
- **More than about 12 Observed entries** usually means two hypotheses. Close the spec (Partial) and open a successor.
- **Shared work:** avoid it. If unavoidable, each spec's entry cites the same commit or PR; don't copy results.

## ADRs

Record one when a choice becomes a constraint future work must honor: component boundary, resource ownership, concurrency model, transport contract, evidence format or trust boundary. Not for bug fixes, settings or UI tweaks. Born Active: decision, one-line alternatives, consequences. Undecided choices are GitHub issues.

**Revoking:** set `Status: Revoked by ADR-NNNN (YYYY-MM-DD): reason`, keep the file, and update inbound links.

## Evidence

Evidence is anything a reader can re-inspect (test, CI run, run directory, benchmark), cited by path or ID. The commit SHA identifies the code, so no source manifests or red/green logs. Keep credentials and private data out of Git.

## Human time

The user's time is scarcest. Prefer automated evidence; ask for a manual trial only for what automation can't test, saying what it tests and which outcome would change the plan. Don't repeat a trial unless its code or conditions changed.

## Sessions

1. **Start:** read [milestones.md](milestones.md) and the active spec, then take its first Open item. If `HANDOFF.md` exists, finish that item first.
2. **Work:** write tests first for code changes. Commit or open a PR. Append the Observed entry with its ref, update check verdicts, and write any ADR in the same change.
3. **End:** update the Open list and any status that changed (child first, then the parent's mirror). Check the word limits.
4. **Stopping early:** write a temporary `HANDOFF.md` at the repo root (where you are, what's half-done, how to resume). The next session deletes it.

**Needs the user:** loosening or removing a check, closing a spec as Partial, marking a goal Met or Dropped, closing a milestone, moving work between milestones, or any change to product intent or scope. Everything else, proceed.
