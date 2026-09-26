# F-0001. Start screen

**Milestone:** [M-0002](../milestones.md#m-0002-explore-the-device)

**Status:** Done (2026-09-26, user-approved)

**Outcome:** The device boots to a start screen with one tile per capability. Each tile shows whether the capability is ready, with a live reading where one exists, and opens that capability's screen. Every screen leads back home.

**Done when:** the user reaches every built capability from home and back without help, and says the screen is clear to read and easy to hit in the hand.

## Assumptions

1. [yes] (T1) A tile grid on the 1280×720 landscape screen is readable and easy to hit while holding the device.
2. [yes] (T1) Tiles can show live readings (motion, power, network) without slowing touch response.
3. [yes] (T1) Home and Back are obvious from every screen.
4. [yes] (T2) Which capability comes first is clear once the user sees the screen: Sound, then its analysis ([F-0002](F-0002-sound-analysis.md)).

## Next

None. Sound analysis continues in [F-0002](F-0002-sound-analysis.md).

## Trials

### T1 2026-09-26: tiles and navigation

`c96557c` · run `20260926-start-screen-t1`. **Tried:** boot to home; each path out and back; tilt; headphones. **Telemetry:** 6 `ui_nav`, touch-down to drawn 166–278 ms (73–130 ms redraw after release); 0 misses; headphone route switched both ways. USB dropped at about 3 min. **User:** "tiles read fine and were easy to hit." **Learned:** the grid works in the hand. **Decision:** continue.

### T2 2026-09-26: Sound instrument

`33b1bf9` · run `20260926-sound-t2`. **Tried:** live spectrum, peak hold, level, Freeze in a café. **Telemetry:** 2 sessions (130 s, 97 s): 23 views/s, compute 9.2 ms mean (14.7 max), 0 driver overflows or short reads; about 12 redraws/s; open/close 173–188 ms. **User:** "works as advertised"; Freeze "not that interesting"; wants an info button per tile with a walkthrough. **Decision:** adapt: drop Freeze, add info.

### T3 2026-09-26: info pages, no Freeze

`6714b45` · run `20260926-info-t3`. **Tried:** info page on Sound and Investigate; Sound without Freeze. **Telemetry:** both pages scrolled to the end (about 5 s open each); no tile opened by mistake; Sound ran 212 s with 0 driver loss. **User:** "info's work, and the descriptions look good"; asked whether Sound could analyze its session. **Decision:** continue.
