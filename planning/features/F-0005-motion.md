# F-0005. Motion instrument

**Milestone:** [M-0002](../milestones.md#m-0002-sensors-explained-by-a-local-llm)

**Status:** Done (2026-11-05, user-approved) · [#3](https://github.com/AlteredCraft/tricorder/issues/3)

**Outcome:** The Motion tile opens a live instrument (acceleration and tilt traces from the BMI270 at 100 Hz). Analysis shows how steady the device was, each jolt, the tilt range and any vibration while it rested on something; Explain has the Mac's local model read it aloud. No voice note.

**Done when:** the user runs it on the device, says the analysis matches what they did, and gets a useful reading from the local model.

## Next

None. Camera ([#4](https://github.com/AlteredCraft/tricorder/issues/4)) follows the same shape.

## Trials

### T1 2026-11-05: Motion screen, analysis and Explain over the hotspot

`f7daf03` · service run `20261105-motion-t1`. **Tried:** live traces, flat / tap / knock / hold / shake, resting on a running object, Analysis, Explain with the local model. **Happened:** "that all works". **Next:** stop.
