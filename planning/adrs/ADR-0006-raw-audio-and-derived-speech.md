# ADR-0006. Preserve raw audio across a separate speech-consumer boundary

Status: Active
Decided: 2026-09-20
Evidence: [G-0001.03 observations](../plans/G-0001.03-audio-integrity.md#observed), especially synthetic speech replay and three live raw/speech captures on 2026-09-20
Replaces: None

## Context

Twenty-four synthetic raw/derived pairs preserve raw input and match the independent speech reference within one PCM count. Three live captures additionally verify 423 ingress-block hashes against saved raw bytes, contiguous capture-relative ranges, zero observed driver loss and exact reference agreement in this run. Source inspection shows the codec wrapper previously discarded actual read sizes, and playback can modify the buffer passed to it.

These results establish the isolated synchronous boundary. They do not establish acquisition under the combined workload, asynchronous buffer lifetime, physical sample-clock accuracy, SD durability or speech-model usefulness.

## Options considered

1. **Modify measurement PCM for speech or playback** — less storage, but destroys the original evidence or makes it depend on consumer order.
2. **Keep raw input immutable and derive owned outputs** — additional buffers and bookkeeping, with independently verifiable provenance and no shared mutable consumer storage.
3. **Shared buffers with asynchronous reference counting** — potentially reduces copies, but introduces lifetime and backpressure behavior not yet tested here.

## Decision

Keep successful codec-read blocks immutable across measurement, speech and playback consumers. Hash at the application ingress boundary before consumers run; retain frame ranges, format, requested gain, clipping and read timing. Account separately for actual driver bytes and queue loss. Saved raw bytes must match those ingress hashes.

Speech receives a separately owned output buffer and carries its source capture ID, slot, frame range and processing configuration. Playback receives copies too. Current consumers finish synchronously and retain only copied history, never producer-buffer pointers. The sequential diagnostic media owner shares the BSP codec handles; this extends the ownership already established by ADR-0003.

## Consequences

Future concurrency must preserve this boundary and explicitly validate any asynchronous ownership scheme before buffers can be reused. Hash integrity does not prove absolute acoustic timing or calibration; read-completion timestamps and capture-relative counters remain labeled accordingly. Physical microphone positions are recorded from fixtures, not inferred from slot numbers.

The current DC rejection/filter/decimation settings are versioned experiment settings, not a permanent speech algorithm or model choice. Combined-load latency, continuous streaming queues, storage and acoustic playback contamination remain open in .02/.03. Change the buffering or scheduling design only with ownership/loss evidence; preserve the original measurement bytes and provenance contract.
