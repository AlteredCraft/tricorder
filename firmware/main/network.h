#pragma once
#include "lvgl.h"
#include <cstddef>
#include <cstdint>
#include "storage_files.h"

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
// True once hotspot credentials were loaded, so the Wi-Fi dialog can return to hotspot mode. Any task.
bool network_hotspot_saved();
// Networks from the SD card that the Wi-Fi dialog offers as one-tap joins. Any task.
void network_set_known(const StorageNetwork* networks, int count);
// Hotspot only: the network name the device broadcasts. Any task.
void network_access_point_name(char* out, size_t size);
// Station only: true while the device broadcasts for the Mac service on this network
// (no answer yet, and no address typed here). Any task.
bool network_service_searching();
