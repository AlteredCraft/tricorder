# ADR-0011. Complete short TCP writes below WebSocket framing

Status: Active · Decided: 2026-09-22 · Evidence: [G-0002.01](../plans/G-0002.01-guided-ab-slice.md#observed)

## Context

The pinned IDF TCP writer calls `send` once and can return a short count. Retrying at the WebSocket layer would insert a new frame header into an unfinished payload.

## Decision

Wrap the TCP parent transport so each already-framed range is written to completion: send only the unsent suffix within the original timeout (one monotonic start per write). Any incomplete range invalidates the connection. Don't append a cancel frame after a failed write. Keep the original socket getter and error handle, because IDF close handling needs them.

**Alternatives:** retry the whole frame (corrupts framing); longer timeouts (doesn't fix short writes).

## Consequences

Depends on the private transport struct, so review on IDF upgrades. Whether this was the historical B-upload failure is unconfirmed.
