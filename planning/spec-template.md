# G-NNNN.nn. Title

Status: Proposed | In progress | Confirmed | Refuted | Partial | Not built
Goal: Link to the one parent G-NNNN, one line saying which outcome this spec serves
ADRs: Links to decisions this experiment tests or informs, or None
Date: YYYY-MM-DD
Revision: Initial proposal. Add dated revision notes before changing hypothesis, workload, scope or thresholds.

## Proposal

### Hypothesis

One paragraph. What we expect to be true once the build has run, stated so that it can be checked from what the system records.

### Refuted if

Concrete observations that would falsify the hypothesis. Distinguish a failed check from missing or inconclusive evidence.

### Build

- Bounded build steps needed to test this hypothesis. Name the mechanism and any prerequisite specs; link architecture rationale in an ADR.

### Out of scope

What this spec deliberately does not test. Link an existing later spec or milestone note where relevant; do not create new documents just to account for exclusions. Exclusions remain Not tested, not implied successes.

### How we know

Write checks before build steps. Name each check's evidence source, expected result and handling of missing data. Label proposed numeric targets. Link shared evidence formats defined by a prerequisite spec rather than copying them. Specify repetition and cross-run comparisons where needed to support the claim.

## Observed

Before any build: "YYYY-MM-DD: Not built, design only." Keep the spec status Not built when recording an unattempted design in a milestone.

Append dated entries per build step. Each names the result (Confirmed, Refuted, Partial, Not tested), what was seen, its evidence path and what changed the design, or "Nothing changed the design." Link an ADR for a consequential architecture decision. Preserve failures and incomplete runs. Identify planning-only revisions separately from measured results.

After each result, reassess status and review linked ADRs whose conditions are affected; update the parent goal and milestone in the same change. For unresolved or deferred work, record the missing evidence, next action and any resumption condition. At closure, account for every check; use Partial when evidence cannot resolve the hypothesis.

- Step N, name (YYYY-MM-DD): Status. What was observed, from which table or log. What changed.
