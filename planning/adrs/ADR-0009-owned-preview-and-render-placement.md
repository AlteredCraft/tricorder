# ADR-0009. Keep preview sources owned and separate rendering from acquisition

Status: Active
Decided: 2026-09-21
Evidence: [G-0001.02 observations](../plans/G-0001.02-concurrent-workload.md#observed), `preview-1`, `preview-core1-1`, `preview-wake-1`
Replaces: None

## Context

The native camera produces1280×720 RGB565 at30fps. The four-buffer FIFO and
owned JPEG path previously passed without live preview. A preview must never
leave LVGL pointing to a camera buffer that capture has already requeued.

The first three-buffer preview run loses seven native completions. Its CPU
snapshots show core1 nearly idle while acquisition and rendering contend on
core0; its preview gaps and source ages also exceed200ms. Moving only LVGL to
core1 restores all1,800 native camera rows. That comparison still fails preview
startup: first panel submission is304ms after the epoch. Creating an LVGL timer
from another task does not interrupt the port's existing idle wait, up to500ms.
Explicitly waking the port after timer installation reduces the observed first
preview submission to121ms.

## Options considered

1. Point LVGL at requeued camera memory — violates renderer ownership.
2. Hold the camera buffer until display finishes — couples acquisition progress
   to rendering and provides no bounded preview replacement policy.
3. Copy a bounded derivative into separate preview storage — isolates ownership
   while retaining native capture and full-resolution JPEG provenance.
4. Increase native buffer count after the first preview loss — adds PSRAM while
   leaving the measured rendering/acquisition scheduling contention unresolved.

## Decision

Keep native acquisition at30fps and retain four capture buffers. Copy every
second delivered camera row to a640×360 RGB565 preview using the top-left pixel
of each2×2 block. Use three fixed460,800-byte preview slots with one producer and
one renderer: writing, pending and displayed. Replace only the pending item;
the displayed slot remains immutable until the renderer selects a replacement
between draws. Count pending replacements separately from selected states that
never reach a panel submission and from repeated renders.

Pin the LVGL task to core1; acquisition remains in the core0 main task. Record
task affinity and base priority in CPU snapshots. Keep other task placement,
camera rates, capture buffer count and JPEG settings unchanged for this decision.
After installing preview or animation timers from another task, explicitly wake
the LVGL port rather than waiting for its old idle timeout.

Retain frame copy/selection records, native sequence/timestamp joins and actual
panel-submission records. Verify the final preview byte-for-byte against an
independent downsample of the retained final native source. Do not identify that
derivative as the native witness in the JPEG assessor.

## Consequences and limits

This lifetime rule depends on pinned LVGL9.2.2's one synchronous software draw
unit with LV_USE_OS=0 under the BSP display lock. Panel DMA consumes separate
LVGL draw buffers. Changing renderer/backend requires renewed lifetime evidence;
asynchronous source readers cannot reuse this release rule unchanged.

The preview consumes1,382,400 bytes of fixed image storage plus bounded trace
rows. The passing camera/preview epoch samples4,865,136 bytes free PSRAM and a
4,718,592-byte largest block. It submits873 of900 produced previews at14.52fps,
counts27 pending replacements, and records maximum gap/source age186/185ms.
All1,800 native frames remain ordered; JPEG worker p95 is140ms. This is measured
contention and memory headroom for this profile, not a maximum-capability claim.

The preview's nominal half-rate policy and200ms gap/age limits do not replace
the original30fps animated UI,100 physical-input events, lossless measurement,
three10-minute combined runs, receiver stall or5% mode-cycle memory-return gates.
Full concurrent acquisition/audio/IMU/UI/network/playback remains to be verified.
The camera-first screen is diagnostic groundwork, not the final investigation UI.
