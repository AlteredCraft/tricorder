# F-0008. Setup copy and known networks

**Milestone:** [M-0002](../milestones.md#m-0002-sensors-explained-by-a-local-llm)

**Status:** Done 2026-11-09 · [#9](https://github.com/AlteredCraft/tricorder/issues/9)

**Outcome:** The Setup screen says which of the two ways to reach the Mac is active (hotspot mode or Wi-Fi mode) and what the other one is. The Wi-Fi dialog shows a button for each known network from the SD card (up to 4, written by `tools.provision_device --known .env.local.<name>`); a tap joins it until restart. In Wi-Fi mode a Back to hotspot button returns to the hotspot without a restart.

**Done when:** the user switches from the hotspot to a known network and back on the device, and Explain works in both.

## Next

Done.

## Trials

### T1 2026-11-09: hotspot to a known network and back, Explain in both

`cd95755` · provisioning run `20261109-provision-known-2` · service run `20261109-power-t1` (the Sound sessions). **Tried:** Wi-Fi setup, tap Newnet; type the Mac's address; Sound, Analysis, Explain; Back to hotspot; Explain again. **Happened:** the device joined Newnet without a restart (192.168.0.66). The address keyboard did not appear at first: it was placed below the screen, fixed in `cd95755`. After that the typed address worked and Explain reached the Mac. "back to hotspot worked, explain worked too". **Next:** stop.
