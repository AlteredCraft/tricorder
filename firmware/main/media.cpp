#include "media.h"
#include "audio_copy.h"
#include "diagnostic_events.h"
#include "bsp/m5stack_tab5.h"
#include "esp_video_init.h"
#include "esp_video_device.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "esp_codec_dev.h"
#include "mbedtls/base64.h"
#include "mbedtls/sha256.h"
#include "linux/videodev2.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <algorithm>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

static bool export_capture(const char* id, const uint8_t* data, size_t size, cJSON* metadata) {
    unsigned char digest[32];
    if (mbedtls_sha256(data, size, digest, 0) != 0) {
        cJSON_Delete(metadata);
        return false;
    }
    char hex[65];
    for (size_t i=0; i<sizeof(digest); ++i) snprintf(hex+i*2, 3, "%02x", digest[i]);
    cJSON_AddStringToObject(metadata, "capture_id", id);
    cJSON_AddNumberToObject(metadata, "size_bytes", size);
    diagnostic_emit(metadata);
    for (size_t offset=0; offset<size; offset+=1024) {
        unsigned char encoded[1369];
        size_t length{};
        if (mbedtls_base64_encode(encoded, sizeof(encoded), &length, data+offset,
                                  std::min(size-offset, size_t(1024))) != 0) return false;
        encoded[length] = 0;
        auto* e = diagnostic_event("capture_chunk");
        cJSON_AddStringToObject(e, "capture_id", id);
        cJSON_AddNumberToObject(e, "offset", offset);
        cJSON_AddStringToObject(e, "data", reinterpret_cast<char*>(encoded));
        diagnostic_emit(e);
        // Bounded serial export for isolated .01 capture, not .02 acquisition.
        vTaskDelay(1);
    }
    auto* e = diagnostic_event("capture_end");
    cJSON_AddStringToObject(e, "capture_id", id);
    cJSON_AddStringToObject(e, "sha256", hex);
    diagnostic_emit(e);
    return true;
}

struct VideoSession {
    int fd = -1;
    bool streaming = false;
    uint8_t* buffers[2]{};
    size_t lengths[2]{};
    ~VideoSession() {
        if (fd < 0) return;
        int type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        if (streaming) ioctl(fd, VIDIOC_STREAMOFF, &type);
        for (int i=0; i<2; ++i)
            if (buffers[i]) munmap(buffers[i], lengths[i]);
        close(fd);
    }
};

void capture_camera(const char* boot_id) {
    diagnostic_stage("TRICORDER / camera capture\n\nHold the device still.\nOne frame will be saved on the Mac.");
    auto fail = [](const char* detail) { diagnostic_check("camera_frame", "fail", detail); };
    esp_video_init_csi_config_t csi{};
    csi.sccb_config.init_sccb = false;
    csi.sccb_config.i2c_handle = bsp_i2c_get_handle();
    csi.sccb_config.freq = 400000;
    csi.reset_pin = -1;
    csi.pwdn_pin = -1;
    esp_video_init_config_t config{};
    config.csi = &csi;
    if (esp_video_init(&config) != ESP_OK) return fail("esp_video_init failed");
    VideoSession video;
    video.fd = open(ESP_VIDEO_MIPI_CSI_DEVICE_NAME, O_RDONLY);
    if (video.fd < 0) return fail("open video failed");
    v4l2_format format{};
    format.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    if (ioctl(video.fd, VIDIOC_G_FMT, &format)) return fail("get video format failed");
    // The vendor G_FMT copies its stored struct, including a zero type field.
    // Preserve the explicit capture type for subsequent calls, as the factory
    // example does by creating a separate format struct before S_FMT.
    if (format.fmt.pix.pixelformat != V4L2_PIX_FMT_RGB565) {
        format.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        format.fmt.pix.pixelformat = V4L2_PIX_FMT_RGB565;
        if (ioctl(video.fd, VIDIOC_S_FMT, &format)) return fail("RGB565 format failed");
    }
    format.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    if (ioctl(video.fd, VIDIOC_G_FMT, &format)) return fail("final video format read failed");
    v4l2_requestbuffers request{};
    request.count = 2;
    request.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    request.memory = V4L2_MEMORY_MMAP;
    if (ioctl(video.fd, VIDIOC_REQBUFS, &request) || request.count != 2)
        return fail("request video buffers failed");
    for (int i=0; i<2; ++i) {
        v4l2_buffer buffer{};
        buffer.type = request.type;
        buffer.memory = request.memory;
        buffer.index = i;
        if (ioctl(video.fd, VIDIOC_QUERYBUF, &buffer)) return fail("query video buffer failed");
        video.lengths[i] = buffer.length;
        video.buffers[i] = static_cast<uint8_t*>(mmap(nullptr, buffer.length, PROT_READ | PROT_WRITE,
                                                     MAP_SHARED, video.fd, buffer.m.offset));
        // esp_video's mmap shim returns nullptr on failure (not POSIX MAP_FAILED).
        if (!video.buffers[i]) return fail("map video buffer failed");
        if (ioctl(video.fd, VIDIOC_QBUF, &buffer)) return fail("queue video buffer failed");
    }
    int type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    if (ioctl(video.fd, VIDIOC_STREAMON, &type)) return fail("start video stream failed");
    video.streaming = true;
    for (int frame=0; frame<10; ++frame) {
        v4l2_buffer buffer{};
        buffer.type = request.type;
        buffer.memory = request.memory;
        if (ioctl(video.fd, VIDIOC_DQBUF, &buffer)) return fail("dequeue video frame failed");
        if (buffer.index >= 2 || !buffer.bytesused || buffer.bytesused > video.lengths[buffer.index])
            return fail("invalid frame size/index");
        if (frame == 9) {
            char id[64];
            snprintf(id, sizeof(id), "%s-camera", boot_id);
            auto* e = diagnostic_event("capture_start");
            cJSON_AddStringToObject(e, "format", "rgb565le");
            cJSON_AddNumberToObject(e, "width", format.fmt.pix.width);
            cJSON_AddNumberToObject(e, "height", format.fmt.pix.height);
            cJSON_AddNumberToObject(e, "stride_bytes", format.fmt.pix.bytesperline);
            cJSON_AddNumberToObject(e, "frame_sequence", buffer.sequence);
            cJSON_AddNumberToObject(e, "dequeue_device_us", esp_timer_get_time());
            cJSON_AddStringToObject(e, "sensor_driver", "SC202CS");
            bool ok = export_capture(id, video.buffers[buffer.index], buffer.bytesused, e);
            diagnostic_check("camera_frame", ok ? "pass" : "fail",
                             "One frame exported; host must independently verify size/hash and visible content.");
        }
        // Keep the dequeued frame owned here until export completes: it cannot
        // be reused by the camera while its bytes are being hashed/transferred.
        if (ioctl(video.fd, VIDIOC_QBUF, &buffer)) return fail("return video buffer failed");
    }
}

static bool play_slots(esp_codec_dev_handle_t speaker, const int16_t* raw, size_t frames,
                       const char* capture_id) {
    unsigned char before[32]{}, after[32]{};
    if (mbedtls_sha256(reinterpret_cast<const uint8_t*>(raw), frames*8, before, 0)) return false;
    bool ok = esp_codec_dev_set_out_vol(speaker, 60) == ESP_OK;
    // Only this small owned copy is passed to the potentially mutating codec.
    int16_t output[512];
    for (unsigned slot=0; slot<4 && ok; ++slot) {
        char text[192];
        snprintf(text, sizeof(text), "PLAYBACK %u of 4 / RAW SLOT %u\n\nListen for your recorded phrase.\nEach slot plays for three seconds.", slot+1, slot);
        diagnostic_stage(text);
        vTaskDelay(pdMS_TO_TICKS(2000));
        auto* e = diagnostic_event("audio_playback_started");
        cJSON_AddStringToObject(e, "capture_id", capture_id);
        cJSON_AddNumberToObject(e, "slot", slot);
        cJSON_AddNumberToObject(e, "volume_percent", 60);
        diagnostic_emit(e);
        ok = esp_codec_dev_set_out_mute(speaker, false) == ESP_OK;
        for (size_t offset=0; offset<frames && ok; offset+=256) {
            size_t count = std::min(size_t(256), frames-offset);
            ok = audio_slot_stereo(raw+offset*4, count, slot, output, 512)
                && esp_codec_dev_write(speaker, output, count*4) == ESP_OK;
        }
        // Allow the final queued samples to drain before muting.
        vTaskDelay(pdMS_TO_TICKS(100));
        ok = esp_codec_dev_set_out_mute(speaker, true) == ESP_OK && ok;
        e = diagnostic_event("audio_playback_finished");
        cJSON_AddStringToObject(e, "capture_id", capture_id);
        cJSON_AddNumberToObject(e, "slot", slot);
        cJSON_AddBoolToObject(e, "write_ok", ok);
        diagnostic_emit(e);
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
    bool unchanged = mbedtls_sha256(reinterpret_cast<const uint8_t*>(raw), frames*8, after, 0) == 0
        && memcmp(before, after, sizeof(before)) == 0;
    char before_hex[65], after_hex[65];
    for (size_t i=0; i<sizeof(before); ++i) {
        snprintf(before_hex+i*2, 3, "%02x", before[i]);
        snprintf(after_hex+i*2, 3, "%02x", after[i]);
    }
    auto* event = diagnostic_event("audio_playback_integrity");
    cJSON_AddStringToObject(event, "capture_id", capture_id);
    cJSON_AddStringToObject(event, "sha256_before", before_hex);
    cJSON_AddStringToObject(event, "sha256_after", after_hex);
    diagnostic_emit(event);
    diagnostic_check("audio_raw_unchanged", unchanged ? "pass" : "fail",
                     "Raw PCM SHA-256 compared before/after playback of separate slot copies.");
    diagnostic_check("audio_playback_write", ok ? "pass" : "fail",
                     "Codec writes only; audible playback requires operator observation.");
    return ok && unchanged;
}

void capture_audio(const char* boot_id, bool playback) {
    // Retain the codec interfaces for repeated tests; the BSP caches its speaker.
    static auto* speaker = bsp_audio_codec_speaker_init();
    static auto* microphone = bsp_audio_codec_microphone_init();
    static unsigned capture_number;
    if (!speaker || !microphone) {
        diagnostic_check("audio_capture", "fail", "codec creation failed");
        return;
    }
    esp_codec_dev_sample_info_t output{};
    output.sample_rate = 48000;
    output.channel = 2;
    output.bits_per_sample = 16;
    esp_codec_dev_sample_info_t input = output;
    input.channel = 4;
    bool ok = esp_codec_dev_open(microphone, &input) == ESP_OK
        && esp_codec_dev_open(speaker, &output) == ESP_OK
        && esp_codec_dev_set_out_mute(speaker, true) == ESP_OK
        && esp_codec_dev_set_in_gain(microphone, 24.0f) == ESP_OK;
    constexpr size_t frames = 48000 * 3;
    constexpr size_t bytes = frames * 4 * sizeof(int16_t);
    auto* pcm = static_cast<uint8_t*>(heap_caps_malloc(bytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
    ok = pcm && ok;
    if (ok && playback) {
        for (int remaining=5; remaining>0; --remaining) {
            char text[192];
            snprintf(text, sizeof(text), "TRICORDER / record in %d\n\nAt RECORDING, say:\nTricorder audio test, one two three.", remaining);
            diagnostic_stage(text);
            vTaskDelay(pdMS_TO_TICKS(1000));
        }
        // Flush queued countdown audio; this is not a continuity measurement.
        ok = esp_codec_dev_read(microphone, pcm, 8192) == ESP_OK;
    }
    int64_t started = esp_timer_get_time();
    if (ok) {
        diagnostic_stage("TRICORDER / RECORDING\n\nSay: Tricorder audio test, one two three.\nThree seconds; speaker muted.");
        diagnostic_emit(diagnostic_event("audio_acquisition_started"));
        for (size_t offset=0; offset<bytes; offset+=8192) {
            int count = std::min(size_t(8192), bytes-offset);
            if (esp_codec_dev_read(microphone, pcm+offset, count) != ESP_OK) { ok = false; break; }
        }
    }
    int64_t ended = esp_timer_get_time();
    if (ok) {
        char id[64];
        snprintf(id, sizeof(id), "%s-audio-%u", boot_id, capture_number++);
        auto* e = diagnostic_event("capture_start");
        cJSON_AddStringToObject(e, "format", "pcm_s16le");
        cJSON_AddNumberToObject(e, "sample_rate_hz", 48000);
        cJSON_AddNumberToObject(e, "channels", 4);
        cJSON_AddNumberToObject(e, "frames", frames);
        cJSON_AddNumberToObject(e, "gain_db", 24);
        cJSON_AddNumberToObject(e, "acquisition_start_us", started);
        cJSON_AddNumberToObject(e, "acquisition_end_us", ended);
        cJSON_AddStringToObject(e, "channel_mapping", "TDM slots 0-3; physical mapping not yet verified");
        cJSON_AddStringToObject(e, "processing", "none; speaker muted; driver loss counters not yet instrumented");
        diagnostic_stage("TRICORDER / saving recording\n\nPlease wait for the playback slot labels.");
        ok = export_capture(id, pcm, bytes, e);
        if (ok && playback) play_slots(speaker, reinterpret_cast<const int16_t*>(pcm), frames, id);
    }
    diagnostic_check("audio_capture", ok ? "pass" : "fail",
                     "Isolated PCM capture/export only; no continuity or acoustic channel-mapping claim.");
    free(pcm);
    esp_codec_dev_close(microphone);
    esp_codec_dev_close(speaker);
}
