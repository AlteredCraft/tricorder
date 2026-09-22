# ADR-0009. Owned preview buffers; LVGL on core 1

Status: Active · Decided: 2026-09-21 · Evidence: [G-0001.02](../plans/G-0001.02-concurrent-workload.md#observed) (`preview-1`, `preview-core1-1`, `preview-wake-1`)

## Context

LVGL can't point at camera buffers that capture has already requeued. With rendering and acquisition both on core 0, 7 frames were lost. Moving LVGL to core 1 fixed that, but a timer created from another task waited up to 500 ms for LVGL's idle wake.

## Decision

Every second camera frame is downsampled to a 640×360 preview (top-left of each 2×2 block) into three fixed 460,800-byte slots: writing, pending and displayed. Only the pending slot is replaced, and the displayed slot stays immutable until the next draw. The LVGL task is pinned to core 1 and acquisition stays on core 0. Call `lvgl_port_task_wake` after installing timers from another task.

## Consequences

Uses 1.38 MB PSRAM. Relies on LVGL 9.2.2's single synchronous draw unit under the BSP lock; a different renderer needs new lifetime evidence. Measured: preview 14.5 fps, max gap 186 ms, all 1,800 native frames kept.
