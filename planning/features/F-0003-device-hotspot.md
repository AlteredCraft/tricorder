# F-0003. Device hotspot and local text model

**Milestone:** [M-0002](../milestones.md#m-0002-explore-the-device)

**Status:** In progress

**Outcome:** The Tricorder broadcasts its own Wi-Fi network. The person joins the Mac to it, starts the service, and Explain or an A/B session works anywhere, with no router, phone hotspot or Internet. The Mac's text model runs locally (Ollama), so the whole loop is offline.

**Done when:** in a place with no usable Wi-Fi, the user joins the Mac to the device, runs Explain with a voice note, and says the answer arrived without any network setup beyond joining the hotspot.

## Assumptions

1. [?] The C6 radio in access-point mode over ESP-Hosted gives the Mac an address and carries a session (uploads of 1.15 MB, spoken replies) as well as a phone hotspot did.
2. [?] Deriving the service address from the DHCP lease (the last device to join) removes every provisioning step except joining the hotspot once.
3. [partly] A local 8B model (gemma4 via Ollama) answers Explain inside the device's 45 s wait with prose that passes the unbacked-number check. Offline smoke on the T4 summary with a note: with reasoning off 3.0 s and passes; with reasoning on it spent the 700-token budget thinking (`20261103-local-explain-smoke`). A/B guidance has a 15 s device deadline; untested with the local model.
4. [?] The Mac keeps Internet by other means when needed; while joined to the device it has none, and the person accepts that.

## Next

T1 (anywhere, 10 minutes, headphones optional): Provision the device for hotspot mode with the ops TUI (`.env.local.tricorder-ap`), join the Mac to the Tricorder network, start the service with `--provider local`, then Sound → listen → Analysis → Voice note → Explain. Then one A/B session. Telemetry: `wifi_access_point`, `wifi_ap_client`, `sound_explain` (connected_ms, replied_ms), `provider_timing` in the service run. Tests assumptions 1–3.

## Trials
