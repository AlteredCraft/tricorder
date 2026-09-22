# ADR-0008. Fail stop before an unresolved JPEG DMA error unwinds

Status: Active · Decided: 2026-09-21 · Evidence: [G-0001.02](../plans/G-0001.02-concurrent-workload.md#observed) (`jpeg-timeout-1`, `jpeg-guard-2`)

## Context

In pinned IDF 5.4.2, `jpeg_encoder_process` queues a stack-local DMA2D descriptor. On timeout its error path calls `dma2d_force_end`, which can't remove a queued transaction and may use a stale channel, then returns and frees the stack. The user approved a hardware fault test, which reproduced the timeout.

## Decision

JPEG runs through a single-owner task guard. A link wrapper on `dma2d_force_end` calls `esp_system_abort` when invoked from the guarded encoder task, before the unsafe unwind. Other callers are passed through unchanged. The fault fixture is compile-time opt-in and off by default.

**Alternatives:** release on error (unsafe); retry force-end (can't cancel); implement DMA2D cancellation (future work).

## Consequences

A real JPEG timeout reboots the device. That is safe but not recovery, and interrupted-measurement handling belongs to G-0001.05. Re-verify on driver/toolchain changes.
