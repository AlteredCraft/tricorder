## G-0002. Prove one usable end-to-end investigation

**Milestone.** [M-0001: Validate the handheld investigation](../milestones.md#m-0001-validate-the-handheld-investigation).

**Outcome.** A person holding the Tricorder can complete one narrow ask → measure → feedback → adjust → compare loop, with guidance grounded in their actual A/B captures, and judge whether it is useful enough to harden.

**Driver.** The [vision](../../vision.md) and the user's 2026-09-21 request to put a thin vertical slice ahead of further broad diagnostic work. Establish product usefulness while retaining the reliability foundations already built.

**Measure.** Recorded mock-agent and live-provider handheld runs demonstrate the complete loop, correct evidence references, explicit failure states and an operator assessment under [G-0002.01](G-0002.01-guided-ab-slice.md). A mock-only demo or attractive UI does not achieve this goal. A negative usefulness result is retained and informs revision, not reported as success.

**Relationship to G-0001.** This is an enabling sibling goal, not a replacement, child goal, or reduced definition of [G-0001](G-0001-trustworthy-live-investigation.md). G-0002 owns early product-flow validation; G-0001 owns full trustworthy-operation acceptance across its five existing specs. Those specs retain their IDs, parent, thresholds and failed evidence. Completing G-0002 does not complete G-0001 or M-0001.

The implementation is shared: build the slice in the existing firmware and Mac service, then harden that same path under G-0001. Do not create a disposable parallel demo or a second competing protocol. G-0002 may begin using verified subsets of .01–.03 before their full acceptance, with unverified limits visible. Fix safety, ownership and evidence-integrity defects encountered in the slice immediately; schedule broader stress/endurance work after the first useful complete loop. Reuse evidence for G-0001 only when it independently satisfies the owning spec's exact workload, instrumentation and repetition requirements.

**Specs.**

- [G-0002.01 Guided A/B vertical slice](G-0002.01-guided-ab-slice.md)

**Status.** In progress. User authorized implementation to resume on 2026-09-21; device mock path builds and boots. Physical trials resumed after the user reported mowing stopped; three corrected developmental mock loops pass technical checks. Controlled delay/cancel/disconnect and fresh recording/guidance recovery have scoped evidence; the mock trial checkpoint is closed. Live work is deferred.

**Progress.** 2026-09-21: User requested this goal and a handoff sequencing change. Next authorized implementation work is G-0002.01: tests and the mock path, then the same path with a live provider and operator feedback. After its outcome is assessed, resume G-0001's full combined-load, interaction, storage, power and recovery gates against the shared implementation. No new build, measurement, completed spec or architectural decision is claimed.

**Progress — 2026-09-21, implementation resumed.** Tests-first host state/evidence contract, bounded WebSocket mock service, and explicit collector spec/revision/workload metadata are implemented. The user selected a steady speaker source; a 20/40 cm fixture is prepared for freezing with the actual source setup before trials. See [protocol checkpoint](../guided-ab-protocol.md). Synthetic host/loopback tests are development evidence only. Firmware transport/UI, three real mock loops, live speech/provider loops and usefulness review remain open. No G-0001 gate is changed.


**Progress — 2026-09-21, device integration.** The shared firmware now includes the bounded C++ state guard, configurable LAN WebSocket client, raw capture ingress proofs, and manual A/B flow. 168 host tests and the P4 trial build pass; device startup is verified. The user is preparing the physical fixture. Three real mock loops, delayed/cancel/disconnect trials, live speech/provider loops and usefulness review remain open; no goal or G-0001 gate is complete.


**Progress — 2026-09-21, first real mock loop.** One complete handheld mock exchange retains and independently verifies both raw captures and response joins. Its steady-tone comparison is misleading because codec-startup transients dominate the measured RMS, so it is retained as failed developmental measurement evidence. A tested/flashed explicit settling prefix awaits a repeat. [ADR-0010](../adrs/ADR-0010-device-owned-ab-lan-experiment.md) adopts only the bounded mock flow/transport supported by the exchange. Imperial 8-inch/16-inch positions and 30% MacBook speaker volume now follow user direction. Formal mock/failure trials, live speech/provider loops and usefulness acceptance remain open.


**Progress — 2026-09-21, settling repeat and live deferral.** The corrected real mock loop passes independent evidence checks, removes the startup spikes and records B/A −6.9860 digital dB. The user confirms completion and explicitly defers live-provider work. Remaining mock repetition/failure checks and fixture characterization stay open. G-0002 cannot be Met on this successful developmental mock alone; its live/usefulness requirements are retained without waiver.


**Disposition — 2026-09-21:** User requested holding off on further physical trials because a lawnmower started outside. All host trial processes are stopped. Resume remaining mock checks in stable background conditions at the user’s request; live work stays separately deferred. One technically verified corrected mock loop does not meet this goal, which remains In progress with unchanged live/usefulness requirements.


**Progress — 2026-09-21, resumed mock repeats.** Two more corrected loops complete and independently pass raw evidence/ACK joins (B/A −7.5752/−9.9557 digital dB). Three developmental mock loops now complete; fixture characterization and controlled failure checks remain. The user reports mowing stopped. Live work stays deferred; no acceptance requirement is waived.


**Progress — 2026-09-21, mock trial closeout.** Three corrected developmental loops, five-second delayed responses, cancellation and service outage/fresh recording-guidance recovery have retained evidence. Trial processes are stopped and trial-4 firmware remains flashed. Full fixture freeze and pending-turn device/panel timing remain limited; failures and malformed serial attachment lines are preserved. See the slice requirement disposition. Live speech/provider and usefulness work remains deferred by the user, so G-0002 is In progress, not Met. ADR-0010 retains its bounded scope.
