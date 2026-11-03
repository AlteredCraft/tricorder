#pragma once
#include "lvgl.h"
#include <cstdint>

// Called with the LVGL lock held; network work runs outside the UI task.
void network_ui_init(lv_obj_t* screen, const char* boot_id);
// Shows the Wi-Fi panel above any open panel. Display lock held.
void network_ui_open();

// Probe the hosted radio from its owning task without joining a network.
bool network_prepare(unsigned timeout_ms);

bool network_connect_saved(const char* ssid, const char* password);
// Hotspot mode (F-0003): broadcast ssid/password (WPA2) so the Mac can join the device.
// The service endpoint follows the last joined device's DHCP lease. Any task.
bool network_start_access_point(const char* ssid, const char* password);
// Own address as esp_netif stores it: the station's, or the hotspot's; 0 while down. Any task.
uint32_t network_ipv4();
// Hotspot only: the last device given an address, 0 when none has one. Any task.
uint32_t network_peer_ipv4();
bool network_access_point();
