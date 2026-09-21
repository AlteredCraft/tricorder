# ADR-0007. Preserve camera completion order with a bounded capture ring

Status: Active
Decided: 2026-09-21
Evidence: [G-0001.02 observations](../plans/G-0001.02-concurrent-workload.md#observed), `jpeg-baseline-1`, `jpeg-ring-1` and `jpeg-fifo-1`
Replaces: None

## Context

Native 1280×720 RGB565 capture runs at 30 Hz. The source hash and copy for one
JPEG every two seconds hold a camera buffer for about 69 ms. With two buffers,
the pinned video shim reuses its active DMA destination when its queue empties,
suppresses delivery, and still invokes the completion observer. The original
run lost 57 sequence IDs between delivered frames and had two further terminal
completions. Counting all 59 as stop discards was unsupported.

Four buffers eliminate observed reuse but expose the shim's newest-first done
list. The first four-buffer run retains all 1,800 frames but fails chronology.
The FIFO candidate delivers 1,800 consecutive frames at 29.999 fps with zero
reuse, order errors or unaccounted completions; all 30 JPEGs independently
decode and their source/copy/post-encode hashes and final raw witness match.

## Options considered

1. Two buffers with synchronous source hash/copy — measured completion loss.
2. Four buffers with unmodified receive order — retains frames but delivers
   accumulated completions in reverse order.
3. Four buffers with FIFO receive for the registered CSI owner — passes the
   current camera/JPEG workload while retaining independent hash checks.

## Decision

Use four fixed camera buffers for this diagnostic profile. For the registered
CSI capture owner, remove the oldest completed buffer under the vendor's stream
lock after taking its existing counting semaphore. Keep callbacks, resource
ownership, buffer flags and other video devices' receive paths intact. Bound
receive waits to two seconds. Count active-buffer reuse explicitly; any reuse,
sequence disorder or unexplained completion remains failure. Stop acquisition
before hashing the final retained image, and measure stop-tail completions from
a separate snapshot.

## Consequences

The ring costs two extra 1,843,200-byte PSRAM buffers. The passing run samples
7,289,732 bytes free PSRAM, with a 7,208,960-byte largest block. This is bounded
headroom for the measured workload, not proof of the full combined memory budget.
The receive adapter depends on pinned private `esp_video` structures and must be
reviewed and retested on a driver upgrade. No preview-drop policy is introduced.

This decision extends ADR-0003's diagnostic foundation; it does not revoke that
ownership decision. Preview/concurrency, allocation-failure recovery, mode-cycle
memory return and JPEG queued-timeout ownership remain unverified. In particular,
the codec's error return alone does not prove a queued DMA transaction has been
cancelled; resolve that path before introducing another DMA2D client.
