# G-0001. A trustworthy live investigation

**Milestone:** [M-0001](../milestones.md#m-0001-validate-the-handheld-investigation)

**Outcome:** A person holding the Tricorder can ask a question, collect and compare evidence, and get guidance while the instrument stays responsive and represents its measurements accurately.

**Measure:** Repeated runs of a complete guided A/B investigation show which capabilities work, that observations are intact, and the response timing, recovery behavior and energy cost. Unsupported capabilities are listed. Numeric targets live in the specs.

**Specs:**

| Spec | Status | State |
| --- | --- | --- |
| [.01 Hardware baseline](G-0001.01-hardware-baseline.md) | In progress | Every built-in peripheral verified individually; ten software resets pass. Cold starts open. |
| [.02 Concurrent workload](G-0001.02-concurrent-workload.md) | In progress | Isolated camera/JPEG/preview, audio, IMU and 30 fps UI baselines pass. Combined runs open. |
| [.03 Audio integrity](G-0001.03-audio-integrity.md) | In progress | Raw/speech separation and on-device FFT verified in isolation. Acoustic/load runs open. |
| [.04 Agent interaction](G-0001.04-agent-interaction.md) | In progress | Mock A/B path and spoken question shared with G-0002. Latency/recovery statistics and spoken output open. |
| [.05 Power and recovery](G-0001.05-power-recovery.md) | Not built | — |

**Status:** In progress. Resumes after G-0002 establishes a useful loop.
