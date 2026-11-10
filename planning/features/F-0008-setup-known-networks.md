# F-0008. Setup copy and known networks

**Milestone:** [M-0002](../milestones.md#m-0002-sensors-explained-by-a-local-llm)

**Status:** In progress · [#9](https://github.com/AlteredCraft/tricorder/issues/9)

**Outcome:** The Setup screen says which of the two ways to reach the Mac is active (hotspot mode or Wi-Fi mode) and what the other one is. The Wi-Fi dialog shows a button for each known network from the SD card (up to 4, written by `tools.provision_device --known .env.local.<name>`); a tap joins it until restart. In Wi-Fi mode a Back to hotspot button returns to the hotspot without a restart.

**Done when:** the user switches from the hotspot to a known network and back on the device, and Explain works in both.

## Next

T1 build is flashed and the SD card holds four known networks (the phone hotspot, Newnet, Nossa-7C_Guest, North Bank internal; run `20261109-provision-known-2`). Trial: open Setup and read the copy; Wi-Fi setup, tap a known network the Mac is also on; Setup shows "Wi-Fi on, device x.x.x.x"; enter the Mac's address; Sound, Analysis, Explain. Then Wi-Fi setup, Back to hotspot, join the Mac to Tricorder, Explain again.

## Trials

None yet.
