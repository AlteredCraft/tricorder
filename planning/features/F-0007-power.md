# F-0007. Power instrument

**Milestone:** [M-0002](../milestones.md#m-0002-sensors-explained-by-a-local-llm)

**Status:** Done 2026-11-09 · [#5](https://github.com/AlteredCraft/tricorder/issues/5)

**Outcome:** The Power tile opens a live instrument (battery volts, current and watts from the INA226 at 10 Hz, 60 s traces). A Screen button steps the backlight 50 → 100 → 20% so one feature's draw can be seen. Analysis shows time on battery, charging and with no current, the volts, the typical, lowest and highest draw and power, the energy used, each change in draw and the draw before and after each Screen tap; Explain has the Mac's local model read it aloud. No voice note, as with Sound, Motion and Camera. Only meaningful on battery: on USB the device runs from USB and the battery branch carries no current.

**Done when:** the user runs it on battery and the model's reading of the power trace makes sense to them.

## Next

Done.

## Trials

### T1 2026-11-09: Power on battery, Analysis and Explain over the hotspot

`c2424a1` · service run `20261109-power-t1`. **Tried:** Power on battery with Screen taps, Analysis, Explain with the local model. **Happened:** the first Explain could not connect to the Mac although the Mac was on the Tricorder network; cause not found (nothing reached the service). After rejoining the network it worked: "analysis and explain worked as expected". **Next:** stop.
