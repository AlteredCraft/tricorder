#pragma once
#include <cstddef>
#include <cstdio>
// access_point: the device broadcasts ssid/password and the Mac joins it (F-0003);
// otherwise it joins that network and talks to endpoint.
// known: other networks the Wi-Fi dialog offers as one-tap joins (issue #9).
struct StorageNetwork { char ssid[33]{}; char password[64]{}; };
constexpr int storage_known_max=4;
struct StorageConfig {
    char ssid[33]{}; char password[64]{}; char endpoint[241]{}; bool access_point=false;
    StorageNetwork known[storage_known_max]{}; int known_count=0;
};
bool storage_config_equal(const StorageConfig& a, const StorageConfig& b);
bool storage_parse_config(const char* json, StorageConfig& out);
bool storage_load_config(const char* directory, StorageConfig& out);
bool storage_replace_config(const char* directory, const char* json);
// Single writer; exclusive .part, fsync, exact readback, then publish by rename.
// Existing final/partial files are preserved. A partial never counts as complete.
bool storage_write_verified(const char* path, const unsigned char* data, size_t size);
