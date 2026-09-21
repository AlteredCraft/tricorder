## G-0002. Prove one usable end-to-end investigation

**Milestone.** [M-0001: Validate the handheld investigation](../milestones.md#m-0001-validate-the-handheld-investigation).

**Outcome.** A person holding the Tricorder can complete one narrow ask → measure → feedback → adjust → compare loop, with guidance grounded in their actual A/B captures, and judge whether it is useful enough to harden.

**Driver.** The [vision](../../vision.md) and the user's 2026-09-21 request to put a thin vertical slice ahead of further broad diagnostic work. Establish product usefulness while retaining the reliability foundations already built.

**Measure.** Recorded mock-agent and live-provider handheld runs demonstrate the complete loop, correct evidence references, explicit failure states and an operator assessment under [G-0002.01](G-0002.01-guided-ab-slice.md). A mock-only demo or attractive UI does not achieve this goal. A negative usefulness result is retained and informs revision, not reported as success.

**Relationship to G-0001.** This is an enabling sibling goal, not a replacement, child goal, or reduced definition of [G-0001](G-0001-trustworthy-live-investigation.md). G-0002 owns early product-flow validation; G-0001 owns full trustworthy-operation acceptance across its five existing specs. Those specs retain their IDs, parent, thresholds and failed evidence. Completing G-0002 does not complete G-0001 or M-0001.

The implementation is shared: build the slice in the existing firmware and Mac service, then harden that same path under G-0001. Do not create a disposable parallel demo or a second competing protocol. G-0002 may begin using verified subsets of .01–.03 before their full acceptance, with unverified limits visible. Fix safety, ownership and evidence-integrity defects encountered in the slice immediately; schedule broader stress/endurance work after the first useful complete loop. Reuse evidence for G-0001 only when it independently satisfies the owning spec's exact workload, instrumentation and repetition requirements.

**Specs.**

- [G-0002.01 Guided A/B vertical slice](G-0002.01-guided-ab-slice.md)

**Status.** In progress. User authorized implementation to resume on 2026-09-21; first host protocol/mock checkpoint built. Handheld/live acceptance remains untested.

**Progress.** 2026-09-21: User requested this goal and a handoff sequencing change. Next authorized implementation work is G-0002.01: tests and the mock path, then the same path with a live provider and operator feedback. After its outcome is assessed, resume G-0001's full combined-load, interaction, storage, power and recovery gates against the shared implementation. No new build, measurement, completed spec or architectural decision is claimed.

**Progress — 2026-09-21, implementation resumed.** Tests-first host state/evidence contract, bounded WebSocket mock service, and explicit collector spec/revision/workload metadata are implemented. The user selected a steady speaker source; a 20/40 cm fixture is prepared for freezing with the actual source setup before trials. See [protocol checkpoint](../guided-ab-protocol.md). Synthetic host/loopback tests are development evidence only. Firmware transport/UI, three real mock loops, live speech/provider loops and usefulness review remain open. No G-0001 gate is changed.
