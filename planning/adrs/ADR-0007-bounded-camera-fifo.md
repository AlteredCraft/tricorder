# ADR-0007. Four camera buffers with FIFO completion

Status: Active · Decided: 2026-09-21 · Evidence: [G-0001.02](../plans/G-0001.02-concurrent-workload.md#observed) (`jpeg-baseline-1`, `jpeg-ring-1`, `jpeg-fifo-1`)

## Context

JPEG source hash/copy holds a camera buffer for about 70 ms. With two buffers, the pinned CSI shim reuses the active DMA buffer and silently suppresses delivery (57 frames lost). With four buffers, its done-list delivers frames newest-first.

## Decision

Use four 1280×720 RGB565 buffers. For the registered CSI owner, `camera_receive.cpp` takes the oldest completed buffer under the vendor stream lock, preserving the semaphore and free flags. Other video devices use the original path. Receive waits are bounded to 2 s. Buffer reuse or out-of-order frames count as failures.

## Consequences

Costs two extra 1.84 MB PSRAM buffers. Depends on private `esp_video` structures, so review and retest on driver upgrades.
