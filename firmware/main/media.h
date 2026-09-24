#pragma once
#include <cstddef>
#include <cstdint>
void capture_camera(const char* boot_id);
void capture_audio(const char* boot_id, bool playback = false);
void set_playback_volume(unsigned volume);
struct cJSON;
bool export_diagnostic_capture(const char* id, const unsigned char* data, size_t size, cJSON* metadata);

inline constexpr unsigned camera_context_settle_frames=15;
struct CameraContextShot {
    unsigned source_width=0,source_height=0,settle_frames=0,luma=0;
    uint64_t sequence=0;int64_t finished_us=0,duration_us=0;
};
// Media owner only: stream, discard settle frames, box-downsample one frame
// into output (RGB565, source an integer multiple of output), stop. Emits
// investigation_context_shot. No audio or display ownership.
bool camera_context_shot(uint16_t* output,size_t output_bytes,unsigned output_width,unsigned output_height,
                         CameraContextShot& shot);
