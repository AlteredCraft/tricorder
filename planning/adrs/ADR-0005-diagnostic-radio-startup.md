# ADR-0005. Diagnostic radio ownership and startup

Status: Active
Decided: 2026-09-20
Evidence: [G-0001.01 — startup failure, allocation limit and correction, 2026-09-20](../plans/G-0001.01-hardware-baseline.md#observed)
Replaces: None

## Context

Adding the pinned factory hosted-radio components exposed a pre-scheduler failure: a timer-task stack landed in TCM, which IDF 5.4.2 rejects for task stacks. Restricting task allocations to SRAM then exposed insufficient early heap. Source inspection identifies hosted initialization in a constructor, before the scheduler releases startup-stack RAM. The corrected device run reaches native media diagnostics; host tests verify deferral and propagation of runtime errors. LAN exchanges remain unverified at this decision.

## Options considered

1. Relax stack assertions or rely on incidental heap layout — avoids the immediate abort without establishing valid memory or a reliable startup order.
2. Change the pinned IDF/vendor sources — potentially removes the incompatibility but requires reproducing the baseline with new inputs.
3. Application-owned lifecycle and explicit task-memory capabilities — preserves pinned sources and assertions, with two small version-specific link wrappers.

## Decision

For this diagnostic, defer hosted initialization until the application network task runs. Constrain FreeRTOS allocator requests to internal, byte-accessible, SIMD-capable SRAM, excluding TCM and RTC RAM. Keep vendor stack checks intact and propagate runtime initialization failures. The application owns network setup; UI callbacks queue work rather than blocking on radio operations.

Diagnostic Wi-Fi credentials are entered on the device, use RAM-only driver storage, and are omitted from diagnostic events. The local HTTP endpoint only echoes bounded nonces and boot/timing metadata. This does not select the later agent transport or authorize internet deployment.

## Consequences

Budget task SRAM separately from general internal free memory in concurrent-workload tests. Retest both wrappers when IDF/hosted versions change; remove them only with replacement evidence. The initial boot fix does not establish network connectivity, sustained concurrency or reset reliability. Credentials must be entered again after a device restart. Preserve the failed startup logs and ELF files in local evidence.
