# ADR-0005. Deferred radio startup and task-memory placement

Status: Active · Decided: 2026-09-20 · Evidence: [G-0001.01](../plans/G-0001.01-hardware-baseline.md#observed) (`acoustic-network-1..3`)

## Context

The hosted-radio (C6) components initialize in a constructor, before the scheduler frees startup RAM. A timer-task stack landed in TCM, which IDF 5.4.2 rejects, and restricting stacks to SRAM then exhausted early heap.

## Decision

Initialize the hosted radio from the application network task, not at construction. Link-wrap FreeRTOS allocations to internal, byte-accessible, SIMD-capable SRAM (no TCM/RTC). Keep vendor stack checks enabled. UI callbacks queue radio work and never block on it.

**Alternatives:** relax assertions (hides the bug); patch pinned IDF (breaks reproduction).

## Consequences

Budget task SRAM separately from general free memory. Retest both wrappers on IDF or hosted upgrades.
