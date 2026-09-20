# Planning guidelines

Keep planning small enough to read and act on. Use milestones, goals and specs for planned work. Retain ADRs for consequential architecture trade-offs. This README and the templates define the conventions; they are not additional project plans.

The planning hierarchy is **Milestone → Goal → Spec**. Each goal has exactly one parent milestone; each spec has exactly one parent goal. Milestones list their goals, and goals list their specs, with a link back to the parent in each child. A milestone may show specs under their owning goal for sequencing, but must not treat specs as direct children. ADRs are linked decision records, not another level in the hierarchy; one can inform several specs or goals.

## Where information belongs

| Artifact | Purpose | Location |
| --- | --- | --- |
| Milestone | A bounded deliverable, its goals, their order and current progress | [milestones.md](milestones.md) |
| Goal | An outcome and how we will know it has been achieved | `planning/plans/G-NNNN-short-title.md` |
| Spec | One hypothesis, the bounded experiment that tests it, its checks and observed results | `planning/plans/G-NNNN.nn-short-title.md` |
| ADR | A consequential decision, alternatives, evidence and costs | `planning/adrs/ADR-NNNN-short-title.md` |

Give each substantive statement one authoritative home; link to it elsewhere. Milestones summarize progress, goals link their specs, and specs link the decisions they test or inform. Avoid copying architecture explanations, acceptance criteria or evidence formats across documents.

Before creating a separate overview, roadmap, validation plan or research summary, check whether the material belongs in an existing artifact. Put relevant research beside the hypothesis or decision it supports. Keep possible future work as a short milestone note until there is a bounded experiment to write. Do not invent a goal or spec merely to give miscellaneous notes a filename. If material genuinely does not fit, discuss its purpose and owner before adding a document type.

## Milestones

[milestones.md](milestones.md) is the entry point and lightweight progress journal. Give each milestone a stable ID (`M-0001`), explicit scope, deliverable and completion condition, and links to its goals. Use status Not started, In progress, Met, or Partly met, derived from the goals. Record sequencing or dependencies here when they span specs, grouped under their owning goals. A list of planned work is not a completed milestone.

## Goals

Use [goal-template.md](goal-template.md). A goal links its parent milestone and states the desired outcome, its driver and how success is measured, with no implementation detail. It can have several serving specs. Use one status field: Not started, In progress, Met, or Partly met, with a brief explanation derived from the specs and the outcome measure. Completing an experiment does not necessarily achieve the goal.

Goals and specs live together in `planning/plans/`. Preserve assigned IDs. For example, `G-0001-trustworthy-live-investigation.md` is served by `G-0001.01-hardware-baseline.md`. There is no separate prototype numbering scheme.

## Specs

Use [spec-template.md](spec-template.md). Each spec serves exactly one goal and tests one hypothesis. Number specs in the order written; never renumber them to change execution order. Keep the scope narrow enough for a human to understand and evaluate independently.

**Proposal** is written before code: hypothesis, refutation conditions, build steps, exclusions and checks. Write the check before each build step. Name the evidence source and expected result, including how missing data is handled. Recorded UI timing or operator observations can be evidence when the spec defines their collection and interpretation; an attractive screenshot alone does not establish correctness.

**Observed** is append-only: dated entries identify the build step, result, evidence location and any design change. Preserve failed and incomplete runs. Link an ADR when a result forces a consequential architecture decision; routine implementation details do not need their own ADR.

Status is Proposed, In progress, Confirmed, Refuted, Partial, or Not built. Proposed denotes a candidate experiment; an unattempted design recorded in a milestone stays Not built, with Observed reading "Not built, design only". Use In progress when execution begins. Confirmed/Refuted describe the hypothesis against its stated checks; Partial identifies what remains unresolved. Missing evidence cannot establish confirmation.

Before changing a proposal's hypothesis, workload, scope or thresholds, add a dated header revision explaining the change. Append the reason under Observed, distinguishing planning changes from measured results. Preserve results under the original revision; do not turn an earlier failure into a pass by changing the criteria.

Evidence requirements belong in a spec's "How we know" section. When several specs share a format, define it once in the spec that establishes it and link that section from the others. Keep only general evidence rules here: distinguish observations from inference, make runs reproducible, and keep credentials and private captures out of the public repository.

## Architecture decision records

Use [adrs/ADR-template.md](adrs/ADR-template.md) for one short record per consequential trade-off. Explain what forced the decision, the alternatives, the choice, its costs and the supporting evidence or unresolved assumptions. Link relevant specs instead of repeating their checks.

Every Proposed ADR must name an owner (a responsible role is sufficient), linked specs, acceptance conditions, and a concrete next review trigger: a spec result, decision event or date. Add dated review entries stating the evidence considered, disposition and remaining blocker. "Review later" is not a trigger. Scope acceptance to the actual decision; optional future capabilities must not keep an otherwise settled decision Proposed indefinitely.

| Status | When to use it |
| --- | --- |
| Proposed | A live decision is unresolved, with a concrete blocker, next action and review trigger. Revise with a dated note when new evidence changes the proposal. |
| Accepted | The choice is adopted within the agreed scope and its stated acceptance conditions are satisfied. Record the date, rationale and evidence links. This does not imply validation beyond that evidence. |
| Rejected | The proposal was evaluated and not selected. Record why and link the alternative if one exists. |
| Withdrawn | The proposal is abandoned, no longer relevant or deferred without an active experiment. Record why; link a future milestone note if appropriate. |
| Superseded by NNNN | An accepted decision has been replaced by a newly accepted ADR. Link both records; a proposed replacement does not yet supersede the active decision. |

Agreement to try a stack is distinct from evidence that it meets the requirements. Once accepted, preserve the decision body; status, supersession links and append-only review history may change. A different decision requires a new ADR. Preserve Rejected/Withdrawn records too; renewed consideration uses a new ADR linked to the earlier rationale.

## Agent lifecycle responsibilities

The agent doing the work maintains the related artifacts in the same change as the implementation or evidence; lifecycle maintenance is part of the task, not a later cleanup. Use the existing files, with no separate status tracker.

1. **At task start:** read the active milestone, parent goal, working spec and linked ADRs. Check their statuses against recorded evidence and changes in user intent. Review every Proposed ADR whose trigger has fired, whose supporting work has ended, or whose next action is missing. Correct stale state before relying on it.
2. **Before a build step:** write its check, confirm prerequisites and set the spec In progress when execution begins. Update parent goal/milestone progress. A documentation-only edit is not a build result.
3. **After a result or scope change:** append the spec evidence/revision, reassess its status, review affected ADRs, then update goal and milestone progress in that order. Evaluate parent outcomes directly; do not equate Confirmed specs with an automatically Met goal. Update any repeated status summaries and links in the same change.
4. **Resolve decisions promptly:** when an ADR's conditions are satisfied, accept it in that update; if evidence rules it out, reject or revise it. Retain Proposed only with the exact missing evidence, a next action and a new concrete review trigger. Withdraw proposals with no active path to a decision. The agent can make these updates within the agreed scope without a separate approval ceremony; ask the user when an unresolved trade-off changes product intent or scope. Do not accept a decision merely to clear a queue.
5. **At task end:** record unresolved work and its next action in the relevant artifact. For deferred or cancelled work, preserve the evidence-derived status and add a dated disposition explaining why work stopped and what would resume it, if anything. Do not leave it described as actively running or silently remove it. Report material status changes and blockers to the user.
6. **At goal/milestone closure:** evaluate the stated outcome/completion condition and record a dated result with evidence links. A milestone cannot be Met with unmet required outcomes or an in-scope Proposed ADR. Resolve those decisions, or explicitly revise scope and preserve the original shortfall and disposition. Carry deferred work forward as a future milestone note; create new goals/specs only when scoped.

If later evidence invalidates a completed outcome, append a dated explanation and reassess the goal/milestone status. Preserve the earlier result and its conditions. Reopen the same spec with a dated revision only for the same bounded hypothesis; use a new spec for a different hypothesis. Never reuse IDs or rewrite old observations to match the current design.
