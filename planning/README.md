# Planning guidelines

Keep planning small enough to read and act on. Use milestones, goals and specs for planned work. ADRs record architectural choices already made from evidence in goals/specs. This README and the templates define the conventions; they are not additional project plans.

The planning hierarchy is **Milestone → Goal → Spec**. Each goal has exactly one parent milestone; each spec has exactly one parent goal. Milestones list their goals, and goals list their specs, with a link back to the parent in each child. A milestone may show specs under their owning goal for sequencing, but must not treat specs as direct children. ADRs are linked decision records, not another level in the hierarchy; one can inform several specs or goals.

## Where information belongs

| Artifact | Purpose | Location |
| --- | --- | --- |
| Milestone | A bounded deliverable, its goals, their order and current progress | [milestones.md](milestones.md) |
| Goal | An outcome and how we will know it has been achieved | `planning/plans/G-NNNN-short-title.md` |
| Spec | One hypothesis, the bounded experiment that tests it, its checks and observed results | `planning/plans/G-NNNN.nn-short-title.md` |
| ADR | An architectural choice already made, its evidence, alternatives and consequences | `planning/adrs/ADR-NNNN-short-title.md` |

Give each substantive statement one authoritative home; link to it elsewhere. Milestones summarize progress, goals link their specs, and specs link decisions they produced or whose assumptions they examine. Candidate approaches and alternatives belong in spec proposals; ADRs explain choices actually made. Avoid copying architecture explanations, acceptance criteria or evidence formats across documents.

Before creating a separate overview, roadmap, validation plan or research summary, check whether the material belongs in an existing artifact. Put relevant research beside the hypothesis or decision it supports. Keep possible future work as a short milestone note until there is a bounded experiment to write. Do not invent a goal or spec merely to give miscellaneous notes a filename. If material genuinely does not fit, discuss its purpose and owner before adding a document type.

## Milestones

[milestones.md](milestones.md) is the entry point and lightweight progress journal. Give each milestone a stable ID (`M-0001`), explicit scope, deliverable and completion condition, and links to its goals. Use status Not started, In progress, Met, or Partly met, derived from the goals. Record sequencing or dependencies here when they span specs, grouped under their owning goals. A list of planned work is not a completed milestone.

## Goals

Use [goal-template.md](goal-template.md). A goal links its parent milestone and states the desired outcome, its driver and how success is measured, with no implementation detail. It can have several serving specs. Use one status field: Not started, In progress, Met, or Partly met, with a brief explanation derived from the specs and the outcome measure. Completing an experiment does not necessarily achieve the goal.

Goals and specs live together in `planning/plans/`. Preserve assigned IDs. For example, `G-0001-trustworthy-live-investigation.md` is served by `G-0001.01-hardware-baseline.md`. There is no separate prototype numbering scheme.

## Specs

Use [spec-template.md](spec-template.md). Each spec serves exactly one goal and tests one hypothesis. Number specs in the order written; never renumber them to change execution order. Keep the scope narrow enough for a human to understand and evaluate independently.

**Proposal** is written before code: hypothesis, refutation conditions, build steps, exclusions and checks. Write the check before each build step. Name the evidence source and expected result, including how missing data is handled. Recorded UI timing or operator observations can be evidence when the spec defines their collection and interpretation; an attractive screenshot alone does not establish correctness.

**Observed** is append-only: dated entries identify the build step, result, evidence location and any design change. Preserve failed and incomplete runs. Record an ADR when evidence leads to an architectural choice, including a deliberate decision to retain an existing approach; routine implementation details do not need their own ADR.

Status is Proposed, In progress, Confirmed, Refuted, Partial, or Not built. Proposed denotes a candidate experiment; an unattempted design recorded in a milestone stays Not built, with Observed reading "Not built, design only". Use In progress when execution begins. Confirmed/Refuted describe the hypothesis against its stated checks; Partial identifies what remains unresolved. Missing evidence cannot establish confirmation.

Before changing a proposal's hypothesis, workload, scope or thresholds, add a dated header revision explaining the change. Append the reason under Observed, distinguishing planning changes from measured results. Preserve results under the original revision; do not turn an earlier failure into a pass by changing the criteria.

Evidence requirements belong in a spec's "How we know" section. When several specs share a format, define it once in the spec that establishes it and link that section from the others. Keep only general evidence rules here: distinguish observations from inference, make runs reproducible, and keep credentials and private captures out of the public repository.

## Architecture decision records

Use [adrs/ADR-template.md](adrs/ADR-template.md) after an architectural choice has been made from evidence recorded in a goal or spec. An ADR is born **Active**. There is no proposal/acceptance queue: undecided alternatives, research, missing evidence and next experiments stay in specs. Agreement to try a candidate stack does not by itself establish an architectural decision to adopt it.

### When to record an ADR

Record one when a choice establishes or changes a durable system constraint: a component/service boundary, firmware framework, peripheral/resource ownership, concurrency model, evidence/storage format, transport contract, or credential/trust boundary. A useful test is whether future work must honor this choice and would need its rationale to change it. Capture a consequential choice to retain an architecture after evaluating alternatives too; reference an existing ADR if it already records the same decision.

Do not create ADRs for every library update, function, bug fix, experiment setting, UI adjustment or planning convention. These belong in specs or the relevant guidance unless they have architectural consequences. Rejected options belong in the chosen decision's alternatives or the experiment results, not in standalone rejected ADRs.

Each ADR must state the choice actually made, its date and scope, alternatives and trade-offs, and links to the specific dated goal/spec evidence that supports it. Source inspection, measured results, failures and constraints can all be evidence when recorded and interpreted in the goal/spec; distinguish them clearly. The entire goal/spec need not be complete, but the evidence must support the bounded decision now. An intention to gather evidence later is insufficient. Record limits and conditions that would warrant reconsideration without implying untested capabilities work.

### Revocation

An ADR stays Active until a new evidence-based decision revokes it. Preserve its original date, context, options, decision and consequences. Add `-R` to its identifier and filename: `ADR-0003-short-title.md` becomes `ADR-0003-R-short-title.md`, titled `ADR-0003-R`. Set Status to Revoked and append a dated **Revocation** section explaining the new goal/spec evidence, why the old decision no longer applies, affected scope, migration/operational consequences, and the replacement ADR if one exists. The suffix marks the original record; it is not a second record or a new numeric ID.

Revocation does not require a replacement. If the choice is now unresolved, state that and link the owning spec's next experiment. If a replacement has been chosen from evidence, create a new Active ADR with the next unused number and link both records. Update inbound links, spec ADR lists and current summaries in the same change; distinguish historical references from current guidance. Keep only the renamed revoked file, not a second copy. Never erase or reactivate a revoked record; a later return to that architecture is a new decision with its own evidence and ID.

### Initial proposal reconciliation

2026-09-20: The former ADR-0001 and ADR-0002 were unvalidated proposals, not decisions in force. Their research and candidate designs now live in [G-0001.01](plans/G-0001.01-hardware-baseline.md#candidate-native-stack) and [G-0001.04](plans/G-0001.04-agent-interaction.md#candidate-service-architecture). Their original files remain in Git history. They are neither Active nor Revoked ADRs. Reserve those numbers for traceability; the first actual ADR will be ADR-0003. No architectural decisions have yet been recorded under this convention.

## Agent lifecycle responsibilities

The agent doing the work maintains the related artifacts in the same change as the implementation or evidence; lifecycle maintenance is part of the task, not a later cleanup. Use the existing files, with no separate status tracker.

1. **At task start:** read the active milestone, parent goal, working spec and linked ADRs. Check statuses against recorded evidence and changes in user intent. Confirm that cited ADRs are Active before treating them as current constraints; read revocations and replacements where present. Keep unresolved architecture questions and their next evidence-gathering steps in the owning spec.
2. **Before a build step:** write its check, confirm prerequisites and set the spec In progress when execution begins. Update parent goal/milestone progress. A documentation-only edit is not a build result.
3. **After a result or scope change:** append the spec evidence/revision, reassess its status, identify architectural choices made or invalidated, then update goal and milestone progress. Evaluate parent outcomes directly; do not equate Confirmed specs with an automatically Met goal. Update repeated summaries and links in the same change.
4. **Capture decisions as they happen:** apply the architectural test above after material experiment results and before finishing work that adopts or changes an architecture. Write the ADR in the same change as the decision, link its evidence, and link it back from the spec's Observed entry and ADR list. If evidence revokes an existing choice, apply the revocation procedure. Do not defer documentation to milestone closure, invent a decision to fill a template, or silently ship an unrecorded architectural choice. The agent can record/revoke decisions within the agreed scope without a separate approval ceremony; ask the user when a trade-off changes product intent or scope.
5. **At task end:** record unresolved work and its next action in the relevant artifact. For deferred or cancelled work, preserve the evidence-derived status and add a dated disposition explaining why work stopped and what would resume it, if anything. Do not leave it described as actively running or silently remove it. Report material status changes and blockers to the user.
6. **At spec/goal/milestone closure:** evaluate the stated checks or outcome and record a dated result with evidence links. Include a brief architecture disposition in the spec's Observed entry: new/revoked ADR links, existing ADRs still applicable, no architectural decision with a reason, or an unresolved question with its missing evidence and next action. Check for decisions made during implementation but never recorded. A milestone cannot be Met with unmet required outcomes, unresolved required architectural choices or unrecorded choices already made. Explicit scope revisions preserve the original shortfall. Carry deferred work forward as a future milestone note; create new goals/specs only when scoped.

If later evidence invalidates a completed outcome, append a dated explanation and reassess the goal/milestone status. Preserve the earlier result and its conditions. Reopen the same spec with a dated revision only for the same bounded hypothesis; use a new spec for a different hypothesis. Never reuse IDs or rewrite old observations to match the current design.
