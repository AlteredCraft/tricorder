#pragma once
// Start screen tile text in tile order (home_model.h grid). `info` is the
// scrolling description behind a tile's info button; nullptr means no button.
// Built-in Montserrat covers ASCII, the degree sign and the bullet only.
namespace home {
struct TileText {const char* name;const char* note;const char* info;};
constexpr TileText tile_text[]={
{"Investigate","Guided sound A/B",
"Compare the sound at two places, with the agent guiding you through the Mac service.\n\n"
"Before you start\n"
"• The Mac service must be running and reachable (see Setup).\n"
"• Headphones are optional. With them plugged in, the speaker stays off.\n\n"
"Walkthrough\n"
"1. Tap Start. The camera takes a context photo, which stays on the device.\n"
"2. Optional: tap Ask, say your question (up to 8 seconds), then tap Stop. Check the transcript and tap Use or Retry.\n"
"3. Hold the device still at place A and tap Record A. The motion label turns green when you are steady.\n"
"4. Listen to the guidance, move to place B, tap Confirm position B, then Record B.\n"
"5. Go back to A and tap Record A again. This checks that A did not change while you were away.\n"
"6. Read or listen to the comparison. A, B and A again are drawn over each other.\n\n"
"What it measures\n"
"The microphone by the hole farther from the USB connector, 3 seconds per recording. The Mac recomputes every number from the raw audio; the model only writes the explanation.\n\n"
"Cancel stops a session at any time. Back returns here."},
{"Sound","Live spectrum",
"A live view of what the microphone hears.\n\n"
"Reading the screen\n"
"• Green line: the sound right now, split into 48 bands from 50 Hz (left) to 20 kHz (right). Higher means louder in that band.\n"
"• Orange line: the loudest each band has been since you opened the screen or tapped Reset peak.\n"
"• The number at the top is the overall level, in dB below the loudest sound the microphone can record (0 dB).\n\n"
"Try it\n"
"1. Stay quiet for a moment to see the background.\n"
"2. Make a sound: tap the table, clink a cup, whistle. Low sounds rise on the left, high sounds on the right.\n"
"3. Tap Reset peak before each new sound to compare them.\n\n"
"Analysis\n"
"Tap Analysis to stop listening and see what happened: the background level, how loud it got, each loud event (10 dB or more above the background) with the band that rose most, any steady tone, and the level over time. It covers up to 10 minutes of listening.\n\n"
"Ask the agent\n"
"1. On the analysis, tap Voice note and say what you heard or want to know, for example \"the grinder ran near the end, which event was it?\" Tap Stop.\n"
"2. The Mac transcribes it and shows what it heard. Tap Explain to send it with the analysis, Record again, or Cancel.\n"
"3. The agent's reading appears above the events and is spoken; Stop voice ends the speech. Explain also works without a note.\n"
"Without the Mac, the note stays on the device and is transcribed when you tap Explain.\n\n"
"Notes\n"
"• The listening audio is never saved or sent. Explain sends the analysis numbers and your voice note to the Mac.\n"
"• The level is not a calibrated sound level. Use it to compare sounds, not as an absolute measurement.\n"
"• The speaker is off while this screen listens."},
{"Camera","Instrument coming",nullptr},
{"Motion","Screen coming",
"The tile shows how far the device is tilted from lying flat, measured by the accelerometer.\n\n"
"• 0° is flat, screen up or down. 90° is standing on an edge.\n"
"• It updates once a second while this screen is showing.\n\n"
"The motion sensor measures the device itself, not the thing you point it at. To measure an object's vibration, the device has to be attached to it.\n\n"
"A full Motion screen is coming."},
{"Power","Screen coming",
"The tile reads the battery through the INA226 power monitor.\n\n"
"• Volts: the battery pack. About 8.4 V is full.\n"
"• Charging: current flowing into the battery, usually with USB plugged in.\n"
"• Using: current drawn from the battery when running on battery power. Watts are volts times amps.\n"
"• No battery current: the battery is neither charging nor in use.\n\n"
"On USB, the device runs from USB, so its own consumption does not show here. Unplug USB to see what it uses.\n\n"
"It updates once a second. A full Power screen is coming."},
{"Audio out","Screen coming",
"Where spoken guidance plays.\n\n"
"• Headphones: something is plugged into the headphone jack, and the speaker is switched off.\n"
"• Speaker: nothing is plugged in, so guidance plays on the built-in speaker, which is quiet.\n\n"
"Plugging in or unplugging during guidance switches the output within a quarter of a second. The tile updates once a second."},
{"Setup","Service and Wi-Fi",
"Connection settings for guided investigations.\n\n"
"Hotspot mode (set up over USB): the device broadcasts its own Wi-Fi network. Join the Mac to it and start the service; the service address fills in by itself when the Mac joins. The tile shows Hotspot on and the Mac's address. No router or Internet is needed; the Mac has no Internet while joined unless it has another connection.\n\n"
"Wi-Fi mode: the device joins a network.\n"
"• The tile shows the device's Wi-Fi address, or Wi-Fi offline.\n"
"• Service address: where the Mac service listens, for example ws://172.20.10.9:8765/. It loads from the SD card at boot; a change made here lasts until restart.\n"
"• Wi-Fi setup: choose a network and enter its password.\n\n"
"Cafe and guest Wi-Fi often stop the device from reaching the Mac. Use hotspot mode there, or a phone hotspot on 2.4 GHz with both the Mac and the device joined to it."},
{"Diagnostics","Hardware checks",
"The hardware check screen used during development.\n\n"
"• Record & play: records a short phrase from all four microphone channels and plays it back.\n"
"• Test 10 restarts and Audio baseline 60s: longer automated checks that report over the USB serial console.\n"
"• Guided A/B: opens the investigation directly.\n"
"• The playback volume slider sets the level for Record & play.\n\n"
"Tap Home at the top right to come back here."},
};
}
