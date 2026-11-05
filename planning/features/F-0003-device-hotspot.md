# F-0003. Device hotspot and local text model

**Milestone:** [M-0002](../milestones.md#m-0002-explore-the-device)

**Status:** In progress

**Outcome:** The Tricorder broadcasts its own Wi-Fi network. The person joins the Mac to it, starts the service, and Explain or an A/B session works anywhere, with no router, phone hotspot or Internet. The Mac's text model runs locally (Ollama), so the whole loop is offline.

**Done when:** in a place with no usable Wi-Fi, the user joins the Mac to the device, runs Explain with a voice note, and says the answer arrived without any network setup beyond joining the hotspot.

## Assumptions

1. [partly] (T1) The C6 radio in access-point mode over ESP-Hosted gives the Mac an address and carries a session (uploads of 1.15 MB, spoken replies) as well as a phone hotspot did. Explain and a 36 s spoken reply worked; no capture upload yet.
2. [yes] (T1) Deriving the service address from the DHCP lease (the last device to join) removes every provisioning step except joining the hotspot once.
3. [partly] (T1) A local 8B model (gemma4 via Ollama) answers Explain inside the device's 45 s wait with prose that passes the unbacked-number check: 4.3 s live, 3.0 s offline with reasoning off (with reasoning on it spent the 700-token budget thinking, `20261103-local-explain-smoke`). A/B guidance has a 15 s device deadline; untested with the local model.
4. [?] The Mac keeps Internet by other means when needed; while joined to the device it has none, and the person accepts that.

## Next

T2 (anywhere, 10 minutes): one A/B session over the hotspot with `--provider local`. Tells us whether the uploads, the 15 s guidance deadline and spoken guidance work with the local model. The user says whether the session completed and the guidance made sense.

## Trials

### T1 2026-11-03: Explain over the hotspot with the local model

`e26eeb8` · run `20261103-hotspot-t1` (service side only: the collector lost USB at 16 min, before the trial) · provisioning `20261103-provision-ap`. **Tried:** provision hotspot mode over USB, Mac joined "Tricorder", voice note, Explain. **Telemetry:** boot straight into hotspot mode (`wifi_address` 192.168.4.1, mode ap); the note "Test zero." transcribed in 0.5 s and the device closed that session without confirming it; a second session ran Explain without a note: local model 4.3 s, reply passed the checks, spoken reply 36 s streamed in 13.8 s, session closed complete. **User:** "the tile shows Mac 192.168.4.2 and explain worked". **Learned:** the whole loop runs with no router and no Internet; device telemetry needs the cable. **Decision:** continue (A/B next).
