# Follow-ups for G-0001

**Paused checkpoint:** no interaction is needed now. The next engineering task is to fix camera completion loss during JPEG source hashing/copying, then repeat the skipped regression stages; see [HANDOFF.md](HANDOFF.md#next-work). All 30 JPEGs decode, but this candidate is not a passing camera workload.

The follow-ups below need your participation or equipment. Progress and evidence stay in [planning/milestones.md](planning/milestones.md); this list is only the handoff to you.

- **Wi-Fi:** after firmware resets, reconnect the Tab5 to the working 2.4 GHz network through its setup screen. Credentials are RAM-only. Needed for device-to-Mac streaming and agent tests; please do not put the password in this file or chat.
- **microSD:** provide a card that may hold disposable test captures. Storage checks, checksum readback and interrupted-write recovery remain untested without one.
- **Cold starts:** help with ten real power-off/on cycles. We will distinguish these from the ten software restarts already passed. Wait for a prepared capture procedure before starting.
- **Audio fixture:** help with repeatable stationary sound/speech tests, including device playback, after the combined workload is ready. Confirm speaker/headphone levels after output adjustments; speaker playback was still faint. The six microphone-position takes are complete; no need to repeat them now.
- **Live agent provider:** choose the model/speech provider and make its credentials available to the Mac service through a local secret/environment configuration. Keep keys out of Git and this file. Mock-provider work can proceed first.
- **Handheld interaction:** when prompted by the prepared test, supply the combined-run touch events, supported touch/motion wake trials, and three guided A/B investigations with responsiveness/usefulness ratings.
- **Battery session:** help with the controlled USB disconnect/power fixtures and a representative 30-minute handheld battery session, including comfort observations. The rear battery is installed; endurance and power-sign/rail checks remain open.

Isolated camera, audio, 100 Hz motion and 30 fps animated-display baselines have passed, along with repeated live raw/speech integrity checks. Full G-0001 acceptance is still in progress.
