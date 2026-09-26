# F-0001. Start screen

**Milestone:** [M-0002](../milestones.md#m-0002-explore-the-device)

**Status:** In progress

**Outcome:** The device boots to a start screen with one tile per capability. Each tile shows whether the capability is ready, with a live reading where one exists, and opens that capability's screen. Every screen leads back home.

**Done when:** the user reaches every built capability from home and back without help, and says the screen is clear to read and easy to hit in the hand.

## Assumptions

1. [?] A tile grid on the 1280×720 landscape screen is readable and easy to hit while holding the device.
2. [?] Tiles can show live readings (motion, power, network) without slowing touch response.
3. [?] Home and Back are obvious from every screen.
4. [?] Which capabilities deserve a tile, and in what order, is clear once the user sees the screen.

## Next

T1 (café, quiet, about 5 minutes on USB): boot to home; open Investigate, Setup and Diagnostics and come back; watch the Motion and Power tiles while tilting the device. Telemetry: `ui_nav` (from, to, touch-down → shown µs) and `home_miss` (taps that hit no tile, x/y). Tests assumptions 1–3.

## Trials
