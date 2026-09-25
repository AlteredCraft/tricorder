#pragma once
#include "lvgl.h"

// Called with the LVGL lock held; network work runs outside the UI task.
void network_ui_init(lv_obj_t* screen, const char* boot_id);
// Shows the Wi-Fi panel above any open panel. Display lock held.
void network_ui_open();

// Probe the hosted radio from its owning task without joining a network.
bool network_prepare(unsigned timeout_ms);

bool network_connect_saved(const char* ssid, const char* password);
