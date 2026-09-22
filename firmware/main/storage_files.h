#pragma once
#include <cstddef>
#include <cstdio>
struct StorageConfig { char ssid[33]{}; char password[64]{}; char endpoint[241]{}; };
bool storage_parse_config(const char* json, StorageConfig& out);
bool storage_load_config(const char* directory, StorageConfig& out);
bool storage_replace_config(const char* directory, const char* json);
bool storage_public_name(const char* name);
// Single writer; exclusive .part, fsync, exact readback, then publish by rename.
// Existing final/partial files are preserved. A partial never counts as complete.
bool storage_write_verified(const char* path, const unsigned char* data, size_t size);
