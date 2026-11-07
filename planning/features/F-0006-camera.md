# F-0006. Camera

**Milestone:** [M-0002](../milestones.md#m-0002-sensors-explained-by-a-local-llm)

**Status:** In progress · [#4](https://github.com/AlteredCraft/tricorder/issues/4)

**Outcome:** The Camera tile opens a live view from the camera. Take photo freezes a 1280 x 720 frame and encodes it as a JPEG on the device; Explain sends the photo to the Mac, where the local vision model (gemma4 in Ollama, over the Responses API the service already uses) answers a fixed "what is this?" and the reading is shown and spoken. No voice note, as with Sound and Motion.

**Done when:** the user photographs a few things, asks what they are, and says the answers were right often enough to be fun.

## Next

T1: open Camera, point it at an object, a label and a page; Take photo, Explain; Retake and ask again. About five minutes, on the hotspot with the local service running (`--provider local`). Watch for a sluggish live view (half-size box average on the media owner, up to 10 frames a second) and for the time from Explain to the first words.

## Trials
