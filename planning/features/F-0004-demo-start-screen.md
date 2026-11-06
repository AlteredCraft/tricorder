# F-0004. Start screen for the demo

**Milestone:** [M-0002](../milestones.md#m-0002-sensors-explained-by-a-local-llm)

**Status:** Done (2026-11-05, user-approved) · [#2](https://github.com/AlteredCraft/tricorder/issues/2)

**Outcome:** The start screen reads as "sensors, explained by the Mac": no Investigate tile, Sound first, and the Setup and Diagnostics text describe Explain rather than guided investigations. The demo (Sound → Analysis → Voice note → Explain) runs over the hotspot with the local model.

**Done when:** the user looks at the start screen, runs the Sound demo over the hotspot, and says nothing on screen points to the dropped investigation.

## Next

None. Follow-ups: Setup screen layout ([#7](https://github.com/AlteredCraft/tricorder/issues/7)), drop the voice note from Sound ([#8](https://github.com/AlteredCraft/tricorder/issues/8)).

## Trials

### T1 2026-11-05: start screen without Investigate; Sound demo over the hotspot

`60b82c4` · service run `20261105-f0004-t1`. **Tried:** six-tile 3x2 start screen, Setup and Diagnostics info pages, Mac on the hotspot, Sound → Analysis → Voice note → Explain with the local model. **Happened:** "screen looks right and explain worked". The Setup screen and its Wi-Fi dialog have layout problems (text clipped at the right edge, dialog wider than the screen, mostly empty screen with a small label). The user wants the voice note out of Sound; voice gets its own demo later. **Next:** stop; follow-ups #7 and #8.
