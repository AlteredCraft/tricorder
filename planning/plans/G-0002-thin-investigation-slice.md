# G-0002. One usable end-to-end investigation

**Milestone:** [M-0001](../milestones.md#m-0001-validate-the-handheld-investigation)

**Status:** Met

**Outcome:** A person holding the Tricorder completes an ask → measure → feedback → adjust → compare loop, gets guidance grounded in their actual A/B captures, and judges whether it is useful enough to harden.

**Measure:** Handheld runs with the mock service and then a live provider complete the loop with correct evidence references and visible failure states, and the operator rates them. A mock-only demo does not count. A negative usefulness result is recorded as a result.

**Relationship to G-0001:** Shares one implementation; does not relax G-0001's checks.

**Specs:**

| Spec | Status |
| --- | --- |
| [.01 Guided A/B vertical slice](G-0002.01-guided-ab-slice.md) | Partial |

**Result:** 2026-09-24 — Live loops with spoken question and guidance: responsiveness 4, usefulness 3 (before the median-level change). The user judged the loop useful enough to harden. Evidence: `20260924-live-loops`, `20260924-spoken-guidance/trial` · `c039103`.
