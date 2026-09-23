# G-0002. One usable end-to-end investigation

**Milestone:** [M-0001](../milestones.md#m-0001-validate-the-handheld-investigation)

**Outcome:** A person holding the Tricorder completes an ask → measure → feedback → adjust → compare loop, gets guidance grounded in their actual A/B captures, and judges whether it is useful enough to harden.

**Driver:** User request (2026-09-21) to validate usefulness before more diagnostic work.

**Measure:** Handheld runs with the mock service and then a live provider complete the loop with correct evidence references and visible failure states, and the operator rates them. A mock-only demo does not count. A negative usefulness result is recorded as a result.

**Relationship to G-0001:** Sibling goal. It shares one implementation and does not replace or relax G-0001's checks.

**Specs:**

| Spec | Status | State |
| --- | --- | --- |
| [.01 Guided A/B vertical slice](G-0002.01-guided-ab-slice.md) | In progress | Mock loop, failure handling, SD archive/replay and live text model work. Next: instrument UI, then speech and three rated live loops. |

**Status:** In progress.
