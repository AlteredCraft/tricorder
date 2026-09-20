# ADR-0003. Pin the Tab5 diagnostic to the reproduced factory foundation

Status: Active
Decided: 2026-09-20
Evidence: [G-0001.01 observations](../plans/G-0001.01-hardware-baseline.md#observed), especially factory reproduction, codec incompatibility and the corrected native diagnostic run
Replaces: None

## Context

Both clean builds of factory `b4e356b` with IDF 5.4.2 boot this P4 v1.3/ST7121 unit. Native register reads identify BMI270 and camera PID `0xeb52`, matching the factory SC202CS driver. Resolving newer codec dependencies breaks the factory BSP API. The BSP convenience display configuration aborts in PPA rotation; the factory full-frame PSRAM configuration runs the native diagnostic without that abort in the recorded short run.

## Options considered

1. **Pinned factory BSP and native IDF** — demonstrated startup and panel coverage; imports vendor driver limitations that require separate checks.
2. **Independent drivers or another BSP** — potentially cleaner APIs, but requires another panel/power bring-up before the experiment can continue.
3. **Floating factory dependencies** — less pin maintenance, but the observed codec compile failure prevents reproduction.

## Decision

Use IDF 5.4.2 and the pinned factory board components as the G-0001 diagnostic foundation. The BSP owns the shared I²C bus, IO-expander power/reset, display and touch; sensor drivers use its bus handle. Pin source commits and resolved component versions. Use the factory full-frame double buffers in PSRAM for the landscape display.

## Consequences

Changes to this foundation require build and on-device regression evidence. Vendor helpers that ignore read errors or report requested byte counts are not sufficient measurement-integrity evidence. Camera naming, functional captures, physical channel mapping, concurrency, calibration, network behavior and power/recovery remain open in the serving specs. This decision establishes diagnostic ownership and build inputs, not completion of the final system architecture or acceptance targets.
