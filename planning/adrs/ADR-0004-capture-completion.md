# ADR-0004. Explicit capture completion; keep partials

Status: Active · Decided: 2026-09-20 · Evidence: [G-0001.01](../plans/G-0001.01-hardware-baseline.md#observed) (`media-boot-2`)

## Decision

Captures are exported as start (ID, format, exact byte count) → ordered chunks → end (SHA-256). The receiver publishes complete metadata only after size and hash match. Interrupted transfers stay marked partial/incomplete, and capture IDs are never overwritten. Raw bytes are kept separately from derived PNG/WAV previews.

**Alternative:** save payloads directly. Simpler, but an incomplete file can look usable.

## Consequences

Consumers must require complete metadata. Completion proves the transfer was intact, not that acquisition was continuous. The same contract applies to the WebSocket upload and SD archive.
