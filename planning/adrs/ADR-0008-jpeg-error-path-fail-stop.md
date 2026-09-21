# ADR-0008. Fail stop before an unresolved JPEG DMA error unwinds

Status: Active
Decided: 2026-09-21
Evidence: [G-0001.02 observations](../plans/G-0001.02-concurrent-workload.md#observed), `jpeg-timeout-1` and `jpeg-guard-2`
Replaces: None

## Context

Pinned IDF 5.4.2 `jpeg_encoder_process` enqueues a pointer to a stack-local
DMA2D transaction configuration. Its `err1` path calls `dma2d_force_end`, ignores
the result, and returns. That function only stops an assigned in-flight RX
channel; it does not remove an unassigned transaction from the pending queue.
On reuse, a transaction can also retain a stale channel pointer. A synchronous
codec error therefore does not establish that its descriptor or input/output
buffers may be released.

Host tests reproduce the discarded-stop-result hazard before adding a guard.
The user-approved hardware fixture reserves P4's sole TX reorder channel without
starting DMA. The real JPEG request queues, times out, and reaches our guard.
The captured next boot reports ESP_RST_PANIC and skips rearming the fixture.
The ordinary run summary remains FAIL; a separate expected-fault assessment
passes only the ordered timeout/guard/reboot observations.

## Options considered

1. Release the source on the codec's error return — unsafe without cancellation.
2. Retry `dma2d_force_end` after return — cannot cancel the queued descriptor and
   can act on a stale channel; also too late to preserve the driver stack.
3. Implement cancellation and quiescence inside the pinned DMA2D scheduler — a
   possible future recovery path, not yet implemented or verified.
4. Fail stop before the unsafe error path unwinds — bounded diagnostic policy
   with a directly reproduced hardware test.

## Decision

Call JPEG through a single-owner task guard. Link-wrap `dma2d_force_end`: when
called synchronously by that guarded encoder task, invoke `esp_system_abort`
before calling the original stop routine or returning through the driver's
error path. Delegate calls from other tasks and ISRs unchanged. Reject overlapping
guarded encoder calls. Clear the guard after normal or pre-enqueue error returns.

The intentional channel-blocking fixture is compile-time opt-in, disabled by
default, and never an acceptance workload. Skip rearming after its panic reboot
and restore normal firmware after the controlled test. Preserve panic evidence.

## Consequences

This is fail-stop ownership protection, not timeout recovery. A real JPEG failure
still fails the zero-crash combined-workload gate and interrupts the investigation.
The device must not pretend to finish a measurement across that reboot. Recovery
and user-facing interrupted-measurement handling remain G-0001.05 work.

The wrapper depends on the pinned driver's error-path calls and linker behavior;
review and reproduce the test on any driver/toolchain change. It conservatively
aborts other guarded `err1` failures as well as queued timeouts. Disassembly of
the archived fixture confirms the driver calls the wrapper before unwinding.

The same guard with fault injection disabled passes the camera/JPEG and all
sequential/live/synthetic regressions. Host AddressSanitizer tests cover seven
resource-acquisition failure points, retained-pool exhaustion, source mutation,
safe codec errors, ten pipeline lifecycles/300 encodes and destruction during an
active encode. These mock-codec tests do not prove vendor-internal allocation
cleanup, device fragmentation, combined-load timing or the 5% memory-return gate.
