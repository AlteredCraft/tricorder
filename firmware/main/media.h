#pragma once
#include <cstddef>
void capture_camera(const char* boot_id);
void capture_audio(const char* boot_id, bool playback = false);
void set_playback_volume(unsigned volume);
struct cJSON;
bool export_diagnostic_capture(const char* id, const unsigned char* data, size_t size, cJSON* metadata);
