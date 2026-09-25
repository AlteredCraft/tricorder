# ADR-0003. Pin the Tab5 firmware to the reproduced factory foundation

Status: Active · Decided: 2026-09-20 · Evidence: [G-0001.01](../plans/G-0001.01-hardware-baseline.md#observed)

## Context

Factory demo `b4e356b` with IDF 5.4.2 builds reproducibly and boots this P4 v1.3 / ST7121 unit. Newer codec dependencies break the factory BSP API. The BSP's default display buffers abort in PPA rotation.

## Decision

Use IDF 5.4.2, LVGL 9.2.2 and the pinned factory board components. The BSP owns the shared I²C bus, IO-expander power/reset, display and touch, and sensor drivers use its bus handle. Use factory full-frame double buffers in PSRAM for the landscape display. Pin source commits and component versions.

**Alternatives:** independent drivers/another BSP (a new panel/power bring-up); floating factory deps (don't compile); Arduino/M5Unified, UIFlow2/MicroPython or Rust esp-hal (none verified for full Tab5 multimedia).

## Consequences

Changing the foundation needs a rebuild plus on-device regression runs. Vendor helpers that ignore errors must be wrapped (see `imu_checked`).

References: [factory demo](https://github.com/m5stack/M5Tab5-UserDemo), [Tab5 BSP](https://components.espressif.com/components/espressif/m5stack_tab5/versions/1.3.0/readme), [Tab5 hardware](https://docs.m5stack.com/en/core/Tab5), [esp_video](https://components.espressif.com/components/espressif/esp_video/versions/2.5.0/readme), [ESP-DSP](https://components.espressif.com/components/espressif/esp-dsp/versions/1.8.2/readme), [ESP-SR](https://github.com/espressif/esp-sr).
