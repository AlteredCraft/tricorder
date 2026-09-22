# ADR-0010. Device-owned A/B flow over a LAN WebSocket

Status: Active · Decided: 2026-09-21 · Evidence: [G-0002.01](../plans/G-0002.01-guided-ab-slice.md#observed)

## Context

The first real mock loop completed with exact raw-hash and request/ACK joins. Native tests reject stale, expired, duplicate and unbacked replies.

## Decision

- Only local buttons start captures. A native reducer on the device validates state, deadlines, session and evidence independently of the host.
- Cancel is local first, then sent to the network. Terminal states need a fresh session, with no auto-retry or reconnect continuation.
- One raw buffer is held until its hash ACK and freed before B. The host recomputes measurements from the bytes, and the device checks them against its own.
- Transport: pinned IDF `tcp_transport` WebSocket, device-initiated, configurable `ws://` endpoint. The Python service holds any provider credentials.
- The fixture lives in one embedded JSON source shared by prompts and evidence.

**Alternatives:** service-initiated captures (weakens local cancel); streaming through the service (unmeasured queues).

## Consequences

Plaintext and LAN only; hosting needs auth/TLS. This is not a speech or calibration decision.
