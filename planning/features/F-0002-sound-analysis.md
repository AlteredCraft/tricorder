# F-0002. Sound session analysis

**Milestone:** [M-0002](../milestones.md#m-0002-explore-the-device)

**Status:** In progress

**Outcome:** After listening on the Sound screen, the person taps Analysis and sees what happened: the background level, how loud it got, each loud event with its strongest band, and any steady tone. Then the agent on the Mac can explain it.

**Done when:** the user says the analysis matches what they heard and tells them something the live view didn't, first on the device alone, then with the agent's reading.

## Assumptions

1. [?] A summary of 48 bands and the level, about 12 times a second, is enough to find the events and steady tones the user heard.
2. [?] The measurements, shown relative to the background, are understandable and useful.
3. [?] Recording the summary doesn't slow the live view (views/s, compute, driver loss).
4. [?] The agent's reading adds something beyond the numbers.

## Next

T4 (café, silent, a few minutes on USB): Sound records a summary; Analysis shows background, loud and maximum levels, events with their strongest band, steady tones, and a level-over-time strip. Device only. Telemetry: `sound_analysis` (every number shown, the per-second level, compute time), `sound_session`. The user notes when loud things happened to compare. Tests assumptions 1–3.

## Trials
