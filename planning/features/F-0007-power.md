# F-0007. Power instrument

**Milestone:** [M-0002](../milestones.md#m-0002-sensors-explained-by-a-local-llm)

**Status:** In progress · [#5](https://github.com/AlteredCraft/tricorder/issues/5)

**Outcome:** The Power tile opens a live instrument (battery volts, current and watts from the INA226 at 10 Hz, 60 s traces). A Screen button steps the backlight 50 → 100 → 20% so one feature's draw can be seen. Analysis shows time on battery, charging and with no current, the volts, the typical, lowest and highest draw and power, the energy used, each change in draw and the draw before and after each Screen tap; Explain has the Mac's local model read it aloud. No voice note, as with Sound, Motion and Camera. Only meaningful on battery: on USB the device runs from USB and the battery branch carries no current.

**Done when:** the user runs it on battery and the model's reading of the power trace makes sense to them.

## Next

T1 build: flash, unplug USB, open Power. Watch the draw settle (about a minute), tap Screen a few times with 5 s or more between taps, plug USB in for the last 10 s, tap Analysis, then Explain. Say whether the numbers and the reading make sense. On a Mac without the toolchain the host tests passed; the firmware build has not been run yet.

## Trials

None yet.
