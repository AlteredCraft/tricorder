# Follow-ups for G-0001 and G-0002

**Paused at the user's request, 2026-09-21:** owned live preview, native camera/JPEG and all sequential/live/synthetic regressions pass; implementation is committed as `11bb278`. The approved JPEG fault test remains retained and its fixture is disabled. All Tricorder collectors have ended. On resumption: [G-0002's thin mock-then-live A/B loop](planning/plans/G-0002-thin-investigation-slice.md), then harden that same path under G-0001's unchanged gates. No physical input is needed now; see [HANDOFF.md](HANDOFF.md#resume-here).

The follow-ups below need your participation or equipment. Progress and evidence stay in [planning/milestones.md](planning/milestones.md); this list is only the handoff to you.

- **Wi-Fi:** after firmware resets, reconnect the Tab5 to the working 2.4 GHz network through its setup screen. Credentials are RAM-only. Needed for device-to-Mac streaming and agent tests; please do not put the password in this file or chat.
- **microSD:** provide a card that may hold disposable test captures. Storage checks, checksum readback and interrupted-write recovery remain untested without one.
- **Cold starts:** help with ten real power-off/on cycles. We will distinguish these from the ten software restarts already passed. Wait for a prepared capture procedure before starting.
- **Audio fixture:** help with repeatable stationary sound/speech tests, including device playback, after the combined workload is ready. Confirm speaker/headphone levels after output adjustments; speaker playback was still faint. The six microphone-position takes are complete; no need to repeat them now.
- **Live agent provider:** choose the model/speech provider and make its credentials available to the Mac service through a local secret/environment configuration. Keep keys out of Git and this file. Mock-provider work can proceed first.
- **Handheld interaction:** first help choose the bounded A/B fixture and run G-0002's prepared mock/live loops with responsiveness/usefulness feedback. Later supply G-0001's combined-run touch events, supported touch/motion wake trials and full guided-investigation acceptance runs. Early slice evidence counts toward those only if it meets their original checks.
- **Battery session:** help with the controlled USB disconnect/power fixtures and a representative 30-minute handheld battery session, including comfort observations. The rear battery is installed; endurance and power-sign/rail checks remain open.

Isolated camera, audio, 100 Hz motion and 30 fps animated-display baselines have passed, along with repeated live raw/speech integrity checks. Full G-0001 acceptance is still in progress.
