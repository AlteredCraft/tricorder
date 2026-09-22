# ADR-0011. Complete short TCP writes below WebSocket framing

Status: Active
Decided: 2026-09-22
Evidence: [G-0002.01 observations](../plans/G-0002.01-guided-ab-slice.md#observed), transport candidate and approved live text probe
Replaces: None

## Context

The pinned IDF TCP writer calls `send` once. Its WebSocket parent writes a frame
header and masked payload separately, and can return a positive short payload
count. Retrying the WebSocket message would insert a new header inside the
unfinished payload. The historical physical B failure did not retain send counts,
so this source defect is not proof of that particular failure's cause.

The native regression verifies byte-exact completion of a 22,000-byte range under
repeated short writes, including varying byte values, and bounded failure for
deadline exhaustion, zero progress, cancellation and errors. The flashed candidate
completes a normal real-device SD replay, independently verified against original
bytes and transcript joins. A receiver delayed by 80 ms per chunk reaches the
unchanged write timeout and fails explicitly. These are not full backpressure
acceptance or fresh microphone measurements.

## Options considered

1. Retry a whole WebSocket frame after a partial TCP write: corrupts framing.
2. Increase timeouts: changes the experiment and does not implement short writes.
3. Complete each already-framed range on a bounded TCP parent adapter.

## Decision

Use option 3 for the device-owned investigation connection. Consume only the
unsent suffix. Decrease the remaining timeout against one monotonic start per
parent write. Invalidate the connection on any incomplete range; never append a
cancel frame after such a failure. A clean connection can still send its bounded
local-cancel notification. Preserve the original TCP socket getter and shared
error foundation, because pinned IDF's close-frame handler requires both.

## Consequences and limits

The adapter owns no extra byte buffer and forwards reads/connect/close/poll to the
existing TCP transport. The media worker owns all handles and frees the wrapper
before its TCP parent. Access to the pinned private transport struct must be
reviewed on IDF upgrades, including graceful close and error propagation.

This extends ADR-0010 without changing its evidence or device ownership contract.
Do not claim the original B failure is reproduced or fixed solely from this
change. Future failures need numeric send diagnostics and retained partials.
