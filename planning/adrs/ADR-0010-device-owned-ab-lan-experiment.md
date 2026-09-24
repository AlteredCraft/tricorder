# ADR-0010. Device-owned A/B flow over a LAN WebSocket

Status: Active · Decided: 2026-09-21 · Revised: 2026-09-24 (operator-owned A/B, repeat of A) · Evidence: [G-0002.01](../plans/G-0002.01-guided-ab-slice.md#observed)

## Context

The first real mock loop completed with exact raw-hash and request/ACK joins. Native tests reject stale, expired, duplicate and unbacked replies.

## Decision

- Only local buttons start captures. A native reducer on the device validates state, deadlines, session and evidence independently of the host.
- Cancel is local first, then sent to the network. Terminal states need a fresh session, with no auto-retry or reconnect continuation.
- One raw buffer is held until its hash ACK and freed before the next capture. The host recomputes measurements from the bytes, and the device checks them against its own.
- Transport: pinned IDF `tcp_transport` WebSocket, device-initiated, configurable `ws://` endpoint. The Python service holds any provider credentials.
- The fixture lives in one embedded JSON source shared with the host, and holds only the capture settings (the evidence contract) and a default question. What A and B are comes from the operator's question and the guidance, not from fixture text.
- A session is A, B and then A again at A's position. The comparison reports B/A next to A-again/A, so a change can be judged against repeat variation. SD replay of a stored pair skips the repeat.

**Alternatives:** service-initiated captures (weakens local cancel); streaming through the service (unmeasured queues).

## Consequences

Plaintext and LAN only; hosting needs auth/TLS. This is not a speech or calibration decision.
