# F-0001. Start screen

**Milestone:** [M-0002](../milestones.md#m-0002-explore-the-device)

**Status:** In progress

**Outcome:** The device boots to a start screen with one tile per capability. Each tile shows whether the capability is ready, with a live reading where one exists, and opens that capability's screen. Every screen leads back home.

**Done when:** the user reaches every built capability from home and back without help, and says the screen is clear to read and easy to hit in the hand.

## Assumptions

1. [yes] (T1) A tile grid on the 1280×720 landscape screen is readable and easy to hit while holding the device.
2. [yes] (T1) Tiles can show live readings (motion, power, network) without slowing touch response.
3. [yes] (T1) Home and Back are obvious from every screen.
4. [?] Which capabilities deserve a tile, and in what order, is clear once the user sees the screen.

## Next

T2 (café, silent, about 5 minutes on USB): the Sound tile opens a live spectrum with peak hold, level, Freeze and Reset peak (user's pick). Watch it follow café sounds (grinder, cups, voices), freeze one, reset, go Home. Telemetry: `sound_session` (views, compute µs, driver overflows/short reads), `sound_control`, `ui_nav`. Tests assumption 4 and whether a live spectrum is worth having.

## Trials

### T1 2026-09-26: tiles and navigation

`c96557c` · run `20260926-start-screen-t1`. **Tried:** boot to home; each path out and back; tilt; headphones. **Telemetry:** 6 `ui_nav`, touch-down to drawn 166–278 ms (73–130 ms redraw after release); 0 misses; headphone route switched both ways. USB dropped at about 3 min. **User:** "tiles read fine and were easy to hit." **Learned:** the grid works in the hand. **Decision:** continue.
