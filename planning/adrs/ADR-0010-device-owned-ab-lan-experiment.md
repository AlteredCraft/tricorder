# ADR-0010. Keep the bounded A/B experiment device-owned across the LAN service

Status: Active
Decided: 2026-09-21
Evidence: [G-0002.01 observations](../plans/G-0002.01-guided-ab-slice.md#observed), especially the first real mock loop, retained startup-transient failure, and native protocol tests
Replaces: None

## Context

The existing media owner can capture and upload two distinct 1,152,000-byte raw
recordings while LVGL handles operator actions. Real session
`ab-5340de189b6408c3fff7faf38ba94c6f` completes A, guidance, explicit adjustment,
B and comparison. Independent assessment confirms raw/ingress hashes, driver
counters, source settings and request/reply/acknowledgement joins. Native tests
reject stale identities, expired requests, duplicate replies, bad settings and
unbacked structured measurements. The operator reports seeing the comparison
and following the 8-inch/16-inch sequence with a continuous source.

The result is nevertheless not a useful steady-tone finding: startup transients
dominate its RMS ratio. Valid transfer and provenance do not establish acoustic
validity. Preserve that failed interpretation and require a separate measurement
correction/repeat. The transport result supports only this bounded experiment.

## Options considered

1. Let service messages start captures or replace device state — weakens local
   cancel and allows late remote work to affect the next physical measurement.
2. Add a parallel media worker or stream live acquisition through the service —
   changes verified codec ownership and adds unmeasured queue/scheduling demands.
3. Reuse the existing media owner, explicit local controls and a bounded
   device-initiated LAN WebSocket connection — the first real mock loop works
   with exact evidence joins; ownership remains inspectable and host-testable.

## Decision

For the G-0002 preset/text mock path, use option 3. Only the device operator can
start A/B. Keep state/deadline/session/evidence validation in a native device
reducer, independently of the host validator. Local cancel invalidates pending
work before network cleanup. Require a fresh session after any terminal state;
there is no automatic capture retry or reconnect continuation. A service reply
and its matching acknowledgement gate adjustment/completion.

Keep one raw PCM buffer until its matching completion/hash acknowledgement;
free it before B. Retain at most two metadata/measurement snapshots and one
outstanding turn. Preserve explicit start/chunk/end completion and incomplete
host files. The host recomputes structured measurements from saved bytes; the
device checks them against its own raw-derived values. Keep provider adapters
behind that contract, with credentials on the Mac.

Reuse pinned IDF `tcp_transport` for the configurable, device-initiated `ws://`
LAN connection and the current bounded Python mock service. This is the shared
implementation to harden, not a second disposable demo. The protocol checkpoint
records the exact message, buffer, timeout and ownership limits.

## Consequences and limits

This selects the bounded mock architecture, not a live provider, speech stack,
production trust boundary or calibrated measurement method. LAN plaintext is
restricted to this experiment; hosted deployment requires its separate trust
and encryption work. Keep the preset fixture in one embedded JSON source so
on-device prompts and evidence agree when units/settings change.

The measured first-loop upload/display flow is not evidence for G-0001's
concurrent workloads, latency distributions, recovery statistics, memory-return
or power gates. Local cancel panel timing, controlled delay/disconnect trials
and live usefulness remain unverified at this decision. Actual UI submission
and audible response must be instrumented before making those claims.

The observed startup problem requires an explicit acquisition-boundary
experiment. The candidate settling prefix is not adopted as sufficient by this
ADR. Never turn a provenance pass into an acoustic-validity claim. Revisit the
transport/ownership choice if the same implementation cannot meet the owning
spec's measured response, concurrency, cancellation or bounded-storage needs.
