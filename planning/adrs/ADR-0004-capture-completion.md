# ADR-0004. Explicit capture completion and retained partials

Status: Active
Decided: 2026-09-20
Evidence: [G-0001.01 — camera and raw export verified, 2026-09-20](../plans/G-0001.01-hardware-baseline.md#observed)
Replaces: None

## Context

The isolated camera/audio run delivered 1,843,200 and 1,152,000 bytes respectively, with independently matching device/host hashes. Receiver tests reject missing, repeated, corrupt and cross-boot data. A previous camera failure remains visible beside a successful audio capture. These results establish transfer integrity, not acquisition continuity.

## Options considered

1. Save serial payloads directly — simple, but incomplete files can resemble usable captures.
2. Explicit start/chunk/end records and checked completion — more metadata and receiver state, but failure leaves attributable partial evidence.

## Decision

For diagnostic exports, identify captures within a boot, declare format and exact byte count, enforce ordered offsets, and require matching SHA-256 before publishing complete metadata. Retain interrupted bytes as partial/incomplete. Keep raw bytes separate from derived PNG/WAV previews. Bound capture size and active transfers. Do not overwrite existing capture identities.

## Consequences

Consumers must require complete metadata and recheck saved size/hash. Completion does not establish uninterrupted sensor acquisition, calibration or physical channel mapping. The current serial/base64 transport is for isolated diagnostics; concurrent streaming and SD crash durability remain experiments. A new transport may preserve this completion contract without retaining its wire encoding. Private captures remain outside Git.
