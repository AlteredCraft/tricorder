# NNNN. Title

Status: Proposed | In progress | Confirmed | Refuted | Partial | Not built
Goal: G-N, one line saying which outcome this spec serves
Date: YYYY-MM-DD (revised YYYY-MM-DD: what changed and why)

## Proposal

### Hypothesis

One paragraph. What we expect to be true once the build has run, stated so that it can be checked from what the system records.

### Refuted if

The observations that would falsify the hypothesis. Concrete: a duplicated row, a manual UI step, a readable row that should not be.

### Build

- What is built, one bullet per component, with the mechanism named (the key, the grant, the join, the task type).
- If time allows: work that extends the hypothesis but is not needed to test it.

### Out of scope

What this spec deliberately does not test, and which later spec or roadmap item takes it. Each item is recorded as Not tested under Observed.

### How we know

One check per build step, read from tables, event logs, or run records. State the query and the expected result. Cross-run checks last.

## Observed

One dated entry per build step, appended in order. Each names the status (Confirmed, Refuted, Partial, Not tested), what was seen and where, and what changed the design, or "Nothing changed the design." Link the ADR when a decision was taken.

- Step N, name (YYYY-MM-DD): Status. What was observed, from which table or log. What changed.
