## G-0001. A trustworthy live investigation

**Milestone.** [M-0001: Validate the handheld investigation](../milestones.md#m-0001-validate-the-handheld-investigation).

**Outcome.** A person holding the Tricorder can ask a question, collect and compare evidence, and receive guidance while the instrument remains responsive and clearly represents what it has measured.

**Driver.** The [vision](../../vision.md): realtime collaboration, tactile use, learning every built-in sensor, and explanations grounded in evidence.

**Measure.** Repeated run records establish the available hardware capabilities, observation integrity, response timing, interruption/recovery behavior and energy cost of a complete guided A/B investigation. Each supported capability has recorded evidence; unavailable or deferred capabilities are explicit. Numeric acceptance targets are proposed in the serving specs.

**Specs.**

- [G-0001.01 Hardware baseline](G-0001.01-hardware-baseline.md)
- [G-0001.02 Concurrent workload](G-0001.02-concurrent-workload.md)
- [G-0001.03 Audio integrity](G-0001.03-audio-integrity.md)
- [G-0001.04 Agent interaction](G-0001.04-agent-interaction.md)
- [G-0001.05 Power and recovery](G-0001.05-power-recovery.md)

**Status.** In progress. Hardware baseline underway; the full investigation and all device acceptance gates remain unverified.

**Progress.** 2026-09-20: Planning only; parent milestone recorded. Next action is G-0001.01's hardware baseline. No outcome evidence exists yet.

**Progress.** 2026-09-20: Started [.01](G-0001.01-hardware-baseline.md#observed): serial access, recovery checks and pinned factory/toolchain setup. Remaining specs are Not built.

**Progress.** 2026-09-20: Factory reproduction and native identity/RTC checks recorded in [.01](G-0001.01-hardware-baseline.md#observed); diagnostic foundation adopted in [ADR-0003](../adrs/ADR-0003-tab5-diagnostic-foundation.md). No SD card; full hardware and guided-investigation gates remain open.
