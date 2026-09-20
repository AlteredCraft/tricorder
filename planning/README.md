# Guidelines for Tricorder Planning via Goals and associated Spec in addition to extracted ADRs

Two artifacts, one direction. A **goal** states an outcome the platform, or the project around it, must produce. A **spec** states one hypothesis about how to reach a goal, what is built to test it, and what was observed. Goals are why; specs are experiments; ADRs (`planning/adrs/`) are the trade-offs those experiments forced.

```
# example goal with specs on the filesystem
plans/G-0001-add-signup-mechanism.md
plans/G-0001.01-config-social-acct-oauth2.md
plans/G-0001.02-build-api-endpoints.md
```

## Goals (`goals/`)

One file per goal, `plans/G-NNNN-short-title.md` from `planning/goal-template.md`. A goal names an outcome and how it would be measured, with **NO** implementation detail. It lists the specs that serve it. A goal often needs more than one spec: each spec tests one hypothesis, and a goal is usually reached through several. A goal's status is read from its specs, not asserted on its own.

## Specs (`specs/`)

One file per hypothesis, `plans/G-NNNN.nn-short-title.md` (e.g. `G-0001.01-`), from `planning/spec-template.md`. Numbered in the order written; never renumbered. A spec serves exactly one goal. Spec 0000, the prototype, serves G-1; the later goals are written from what it taught.

A spec has two halves. **Proposal** is written before any code and changes only through a dated revision note in its header: the hypothesis, what would refute it, what is built, what is deliberately out of scope, and how the result will be read from what the system records. **Observed** is appended as the work happens: one dated entry per build step, each saying what was checked, in which table or log, and what, if anything, changed the design. A change of design goes to an ADR; the entry links it.

Status is one of Proposed, In progress, Confirmed, Refuted, Partial, or Not built. A spec whose build is not attempted for the review stays Not built, with Observed reading "Not built, design only", and appears in `docs/roadmap.md` as a phase 1 iteration.

## Rules

- Write the spec before the code, and the check before the build step. "How we know" names tables, event logs, and run records, never the UI.
- Observed records what was seen, including refutations and partials. Positive framing is fine; fabrication and untested claims are not.
- Keep the Proposal stable. If the build teaches something that changes the hypothesis, note the revision and date in the header and say what changed in Observed, so the reader can see the iteration.

## Architecture Decision Records

One short record per real trade-off. Numbered, never edited after acceptance; a change of mind is a new ADR that supersedes the old one.

Format: `ADR-NNNN-short-title.md`, from `planning/adrs/ADR-template.md`. Status is one of Proposed, Accepted, Superseded by NNNN.

An ADR answers: what forced a decision, what the options were, what was chosen, and what that costs. Decisions driven by evidence gathered during the build (a doc passage, a dev-deploy result, a limit hit) are the most useful ones to record.
