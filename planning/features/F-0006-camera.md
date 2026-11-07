# F-0006. Camera

**Milestone:** [M-0002](../milestones.md#m-0002-sensors-explained-by-a-local-llm)

**Status:** Done 2026-11-07 · [#4](https://github.com/AlteredCraft/tricorder/issues/4)

**Outcome:** The Camera tile opens a live view from the camera. Take photo freezes a 1280 x 720 frame and encodes it as a JPEG on the device; Explain sends the photo to the Mac, where the local vision model (gemma4 in Ollama, over the Responses API the service already uses) answers a fixed "what is this?" and the reading is shown and spoken. No voice note, as with Sound and Motion.

**Done when:** the user photographs a few things, asks what they are, and says the answers were right often enough to be fun.

## Next

Done.

## Trials

### T1 2026-11-07: Camera screen, photo and Explain over the hotspot

`c61d085` · service run `20261107-camera-t1`. **Tried:** live view, Take photo, Explain with the local vision model, Retake and ask again. **Happened:** "the test worked, agent reported a proper description, latency was low". **Next:** stop.
