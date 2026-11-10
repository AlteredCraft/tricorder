#pragma once
#include "lvgl.h"
#include <cstddef>
// Setup screen (F-0004): live network and audio-out state, the Mac service address
// and Wi-Fi setup. setup_ui_init and setup_open need the display lock.
enum class EndpointSource {Default,Sd,Hotspot,Typed};
void setup_ui_init(lv_obj_t* screen);
void setup_open();
// Any task: the Mac service address, and where it came from.
void setup_set_endpoint(const char* endpoint,EndpointSource source);
// Any task: the address Explain connects to. Empty in hotspot mode until the Mac joins,
// since the stored one is then an old lease or the SD value, neither on this network.
void setup_endpoint(char* out,size_t size);
