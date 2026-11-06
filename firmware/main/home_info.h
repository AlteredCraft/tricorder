#pragma once
// Start screen tile text in tile order (home_model.h grid). `info` is the
// scrolling description behind a tile's info button; nullptr means no button.
// Built-in Montserrat covers ASCII, the degree sign and the bullet only.
namespace home {
struct TileText {const char* name;const char* note;const char* info;};
constexpr TileText tile_text[]={
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
"1. On the analysis, tap Explain to send the analysis to the Mac.\n"
"2. The agent's reading appears above the events and is spoken; Stop voice ends the speech.\n\n"
"Notes\n"
"• The listening audio is never saved or sent. Explain sends only the analysis numbers to the Mac.\n"
"• The level is not a calibrated sound level. Use it to compare sounds, not as an absolute measurement.\n"
"• The speaker is off while this screen listens."},
{"Motion","Movement and vibration",
"A live view of how the device moves, from its accelerometer, 100 times a second. The tile shows how far the device is tilted from lying flat, once a second.\n\n"
"Reading the screen\n"
"• Green trace: acceleration minus gravity over the last 6 seconds, in g (1 g is the pull of gravity; mg is a thousandth of that). It sits near 0 when the device is still and jumps when it is tapped, bumped or shaken. The scale grows to fit.\n"
"• Blue trace: tilt from lying flat. 0° is flat, screen up or down; 90° is standing on an edge.\n"
"• Tilt at the top is the tilt right now. Peak is the biggest jump since you opened the screen or tapped Reset peak.\n\n"
"Try it\n"
"1. Set the device on a table and keep still for a few seconds.\n"
"2. Tap the table next to it, then knock on the device.\n"
"3. Pick it up and hold it, then shake it.\n"
"4. Set it on something running, such as a washing machine, a fan's base or a laptop with its fan on, and leave it there for 10 seconds or more.\n\n"
"Analysis\n"
"Tap Analysis to stop measuring and see what happened: how steady it was (held still, in hand or moving, from the spread of the acceleration in each second), the steadiest and shakiest second, each jolt (0.1 g or more above the quiet level) with its time, length and size, the range of tilt and the usual orientation, and any vibration. It covers up to 10 minutes.\n\n"
"Vibration is measured only while the device rests on something for at least 4 seconds. The analysis reports the strongest repeating frequency, in Hz, and its size, when one stands out.\n\n"
"Ask the agent\n"
"1. On the analysis, tap Explain to send the analysis to the Mac.\n"
"2. The agent's reading appears above the jolts and is spoken; Stop voice ends the speech.\n\n"
"Notes\n"
"• The sensor measures the device itself, not what you point it at. To measure something's vibration, set the device on it.\n"
"• The readings are not calibrated. Use them to compare, not as exact measurements.\n"
"• Vibration faster than 50 times a second can show up at a lower frequency.\n"
"• The samples are never saved or sent. Explain sends only the analysis numbers to the Mac."},
{"Camera","Instrument coming",nullptr},
{"Power","Screen coming",
"The tile reads the battery through the INA226 power monitor.\n\n"
"• Volts: the battery pack. About 8.4 V is full.\n"
"• Charging: current flowing into the battery, usually with USB plugged in.\n"
"• Using: current drawn from the battery when running on battery power. Watts are volts times amps.\n"
"• No battery current: the battery is neither charging nor in use.\n\n"
"On USB, the device runs from USB, so its own consumption does not show here. Unplug USB to see what it uses.\n\n"
"It updates once a second. A full Power screen is coming."},
{"Setup","Mac, Wi-Fi, audio out",
"How the device reaches the Mac service, which runs Explain with a local model.\n\n"
"Hotspot mode (the default, set up over USB): the device broadcasts its own Wi-Fi network, \"Tricorder\". Join the Mac to it and start the service; the service address fills in from the Mac's DHCP lease. The tile shows Hotspot on and the Mac's address, for example Mac 192.168.4.2. No router or Internet is needed; the Mac has no Internet while joined unless it has another connection.\n\n"
"Wi-Fi mode: the device joins a network.\n"
"• The tile shows the device's Wi-Fi address, or Wi-Fi offline.\n"
"• Service address: where the Mac service listens, for example ws://172.20.10.9:8765/. It loads from the SD card at boot; a change made here lasts until restart.\n"
"• Wi-Fi setup: choose a network and enter its password.\n"
"Cafe and guest Wi-Fi often stop the device from reaching the Mac; use hotspot mode there.\n\n"
"Audio out\n"
"The tile's last line shows where the agent's voice plays.\n"
"• Headphones: something is plugged into the headphone jack, and the speaker is switched off.\n"
"• Speaker: nothing is plugged in, so it plays on the built-in speaker, which is quiet.\n"
"Plugging in or unplugging switches the output within a quarter of a second."},
{"Diagnostics","Hardware checks",
"The hardware check screen used during development.\n\n"
"• Record & play: records a short phrase from all four microphone channels and plays it back.\n"
"• Test 10 restarts and Audio baseline 60s: longer automated checks that report over the USB serial console.\n"
"• The playback volume slider sets the level for Record & play.\n\n"
"Tap Home at the top right to come back here."},
};
}
