#pragma once
#include <atomic>
#include <cstddef>
#include <cstdint>
void capture_camera(const char* boot_id);
void capture_audio(const char* boot_id, bool playback = false);
void set_playback_volume(unsigned volume);
struct cJSON;
bool export_diagnostic_capture(const char* id, const unsigned char* data, size_t size, cJSON* metadata);

// Media owner only (F-0006): stream RGB565 frames, calling sink for each one while it
// returns true and stop is clear; the frame is owned until sink returns. Emits
// camera_stream. False when the camera could not be opened; error names the step.
using CameraFrameSink=bool(*)(const uint16_t* pixels,unsigned width,unsigned height,void* user);
bool camera_stream(const std::atomic<bool>& stop,CameraFrameSink sink,void* user,const char** error);
