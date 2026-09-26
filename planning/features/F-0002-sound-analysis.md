# F-0002. Sound session analysis

**Milestone:** [M-0002](../milestones.md#m-0002-explore-the-device)

**Status:** In progress

**Outcome:** After listening on the Sound screen, the person taps Analysis and sees what happened: the background level, how loud it got, each loud event with its strongest band, and any steady tone. Then the agent on the Mac can explain it.

**Done when:** the user says the analysis matches what they heard and tells them something the live view didn't, first on the device alone, then with the agent's reading.

## Assumptions

1. [partly] (T4) A summary of 48 bands and the level, about 12 times a second, is enough to find the events and steady tones the user heard. Sounds shorter than 0.3 s (taps, clinks) are missed.
2. [yes] (T4) The measurements, shown relative to the background, are understandable and useful.
3. [yes] (T4) Recording the summary doesn't slow the live view (views/s, compute, driver loss).
4. [?] A voice note from the user steers the agent, and the agent's reading adds something beyond the numbers.

## Next

T5 (hotspot, a few minutes, headphones): on Analysis, record a voice note (what you heard, what you want to know), then Explain sends the summary and note to the Mac. The note is transcribed and the agent's reading is shown and spoken. Short loud sounds are listed as "sharp sounds". Telemetry: `sound_explain` (stages, timings), the service run. Tests assumption 4.

## Trials

### T4 2026-09-26: on-device analysis

`7eee98e` · run `20260926-sound-analysis-t4`. **Tried:** listen, Analysis, Listen again (sessions of 12, 5 and 41 s). **Telemetry:** analysis 2–4 ms; recording added 0.6 ms per view, 0 driver loss. A +28 dB moment at 0:08 lasted under 0.3 s, so it wasn't listed; one 0.34 s event near 6.1 kHz was. "Strongest near 53 Hz" comes from bands narrower than one FFT bin. **User:** "looks good"; wants a voice note on Analysis to steer the agent. **Decision:** continue.
