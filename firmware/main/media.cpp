#include "media.h"
#include "audio_copy.h"
#include "audio_ingress.h"
#include "audio_devices.h"
#include "camera_baseline.h"
#include "camera_ingress.h"
#include "speech_filter.h"
#include "diagnostic_events.h"
#include "bsp/m5stack_tab5.h"
#include "esp_video_init.h"
#include "esp_video_device.h"
#include "esp_video_ioctl.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "esp_codec_dev.h"
#include "mbedtls/base64.h"
#include "mbedtls/sha256.h"
#include "linux/videodev2.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <algorithm>
#include <atomic>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

bool export_diagnostic_capture(const char* id, const uint8_t* data, size_t size, cJSON* metadata) {
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
    diagnostic_stage("CAMERA BASELINE / 60 seconds\n\nAutomatic frame timing and loss checks.\nPlease leave the device powered and connected.");
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
    auto* capabilities=diagnostic_event("camera_capabilities");
    esp_cam_sensor_format_t sensor{};
    int sensor_result=ioctl(video.fd,VIDIOC_G_SENSOR_FMT,&sensor);
    cJSON_AddBoolToObject(capabilities,"sensor_format_read",sensor_result==0);
    if (!sensor_result) {
        cJSON_AddStringToObject(capabilities,"sensor_mode",sensor.name ? sensor.name:"unknown");
        cJSON_AddNumberToObject(capabilities,"sensor_width",sensor.width);
        cJSON_AddNumberToObject(capabilities,"sensor_height",sensor.height);
        cJSON_AddNumberToObject(capabilities,"sensor_fps_nominal",sensor.fps);
    }
    auto* formats=cJSON_AddArrayToObject(capabilities,"pixel_formats");
    for (unsigned index=0;index<16;++index) {
        v4l2_fmtdesc item{};item.type=V4L2_BUF_TYPE_VIDEO_CAPTURE;item.index=index;
        if (ioctl(video.fd,VIDIOC_ENUM_FMT,&item)) {
            cJSON_AddNumberToObject(capabilities,"format_enum_end_errno",errno);break;
        }
        cJSON_AddItemToArray(formats,cJSON_CreateNumber(item.pixelformat));
    }
    auto requested=format;requested.type=V4L2_BUF_TYPE_VIDEO_CAPTURE;
    requested.fmt.pix.width=640;requested.fmt.pix.height=480;requested.fmt.pix.pixelformat=V4L2_PIX_FMT_RGB565;
    int requested_result=ioctl(video.fd,VIDIOC_S_FMT,&requested);
    cJSON_AddBoolToObject(capabilities,"request_640x480_accepted",requested_result==0);
    if (requested_result) cJSON_AddNumberToObject(capabilities,"request_640x480_errno",errno);
    format.type=V4L2_BUF_TYPE_VIDEO_CAPTURE;
    if (ioctl(video.fd,VIDIOC_G_FMT,&format)) {cJSON_Delete(capabilities);return fail("post-probe format read failed");}
    cJSON_AddNumberToObject(capabilities,"selected_width",format.fmt.pix.width);
    cJSON_AddNumberToObject(capabilities,"selected_height",format.fmt.pix.height);
    diagnostic_emit(capabilities);
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
    configure_camera_ingress(size_t(format.fmt.pix.width)*format.fmt.pix.height*2);
    if (ioctl(video.fd, VIDIOC_STREAMON, &type)) return fail("start video stream failed");
    video.streaming = true;
    v4l2_buffer buffer{};
    int64_t dequeued_us=0;
    if (!run_camera_baseline(video.fd,format,video.buffers,video.lengths,boot_id,buffer,dequeued_us))
        return fail("camera baseline did not retain a stopped-stream image");
    video.streaming=false;
    {
            char id[64];
            snprintf(id, sizeof(id), "%s-camera", boot_id);
            auto* e = diagnostic_event("capture_start");
            cJSON_AddStringToObject(e, "format", "rgb565le");
            cJSON_AddNumberToObject(e, "width", format.fmt.pix.width);
            cJSON_AddNumberToObject(e, "height", format.fmt.pix.height);
            cJSON_AddNumberToObject(e, "stride_bytes", format.fmt.pix.bytesperline);
            CameraFrameEvidence evidence;
            if (camera_frame_evidence(video.buffers[buffer.index],evidence)) {
                cJSON_AddNumberToObject(e,"completion_sequence",evidence.sequence);
                cJSON_AddNumberToObject(e,"completion_device_us",evidence.finished_us);
            }
            cJSON_AddNumberToObject(e, "driver_frame_sequence_unpopulated", buffer.sequence);
            cJSON_AddNumberToObject(e, "dequeue_device_us", dequeued_us);
            cJSON_AddStringToObject(e, "sensor_driver", "SC202CS");
            bool ok = export_diagnostic_capture(id, video.buffers[buffer.index], buffer.bytesused, e);
            diagnostic_check("camera_frame", ok ? "pass" : "fail",
                             "One frame exported; host must independently verify size/hash and visible content.");
    }
}

static std::atomic<unsigned> playback_volume{80};

void set_playback_volume(unsigned volume) {
    playback_volume.store(std::min(volume, 100U));
}

static bool play_slots(esp_codec_dev_handle_t speaker, const int16_t* raw, size_t frames,
                       const char* capture_id) {
    unsigned char before[32]{}, after[32]{};
    if (mbedtls_sha256(reinterpret_cast<const uint8_t*>(raw), frames*8, before, 0)) return false;
    // Snapshot once so all slots in this comparison use identical output gain.
    unsigned volume = playback_volume.load();
    bool ok = esp_codec_dev_set_out_vol(speaker, volume) == ESP_OK;
    // Only this small owned copy is passed to the potentially mutating codec.
    int16_t output[512];
    for (unsigned slot=0; slot<4 && ok; ++slot) {
        char text[192];
        const char* take=strstr(capture_id,"-audio-");
        snprintf(text, sizeof(text), "TAKE %s\nPLAYBACK %u of 4 / RAW SLOT %u\n\nListen for your recorded phrase.", take ? take+1:capture_id,slot+1,slot);
        diagnostic_stage(text);
        vTaskDelay(pdMS_TO_TICKS(2000));
        auto* e = diagnostic_event("audio_playback_started");
        cJSON_AddStringToObject(e, "capture_id", capture_id);
        cJSON_AddNumberToObject(e, "slot", slot);
        cJSON_AddNumberToObject(e, "volume_percent", volume);
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

struct AudioBlockEvidence {
    size_t source_start=0,frames=0;
    int64_t read_end_us=0,ready_us=0,compute_us=0;
    char sha256[65]{};
    unsigned clipped[4]{};
    bool unchanged=false;
};

static bool hash_audio_block(const uint8_t* data,size_t bytes,char* hex) {
    unsigned char digest[32];
    if (mbedtls_sha256(data,bytes,digest,0)) return false;
    for (size_t i=0;i<32;++i) snprintf(hex+i*2,3,"%02x",digest[i]);
    return true;
}

void capture_audio(const char* boot_id, bool playback) {
    // Retain the codec interfaces for repeated tests; the BSP caches its speaker.
    auto speaker = diagnostic_speaker();
    auto microphone = diagnostic_microphone();
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
    char id[64];
    snprintf(id,sizeof(id),"%s-audio-%u",boot_id,capture_number++);
    auto* pcm = static_cast<uint8_t*>(heap_caps_malloc(bytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
    constexpr size_t block_bytes=8192,max_blocks=(bytes+block_bytes-1)/block_bytes;
    auto* proofs=static_cast<AudioBlockEvidence*>(heap_caps_calloc(max_blocks,sizeof(AudioBlockEvidence),MALLOC_CAP_SPIRAM));
    auto* speech=static_cast<int16_t*>(heap_caps_malloc((frames/3)*2,MALLOC_CAP_SPIRAM));
    SpeechFilter filter(true,4,0);
    size_t block_count=0,speech_frames=0,input_clipped=0,output_clipped=0;
    int64_t speech_compute_us=0;
    ok = pcm && proofs && speech && ok;
    if (ok && playback) {
        for (int remaining=5; remaining>0; --remaining) {
            char text[192];
            snprintf(text, sizeof(text), "TAKE audio-%u / record in %d\n\nAt RECORDING, say:\nTricorder audio test, one two three.",capture_number-1,remaining);
            diagnostic_stage(text);
            vTaskDelay(pdMS_TO_TICKS(1000));
        }
    }
    AudioIngressSnapshot before{},after{};
    int64_t started=esp_timer_get_time();
    if (ok) {
        char text[192];
        snprintf(text,sizeof(text),"TAKE audio-%u / RECORDING\n\nSay: Tricorder audio test, one two three.\nThree seconds; speaker muted.",capture_number-1);
        diagnostic_stage(text);
        diagnostic_emit(diagnostic_event("audio_acquisition_started"));
        started=esp_timer_get_time();
        ok=begin_audio_epoch(before);
        for (size_t offset=0; ok && offset<bytes; offset+=block_bytes) {
            int count = std::min(block_bytes, bytes-offset);
            if (esp_codec_dev_read(microphone, pcm+offset, count) != ESP_OK) { ok = false; break; }
            auto& proof=proofs[block_count];
            proof.source_start=offset/8;proof.frames=count/8;proof.read_end_us=esp_timer_get_time();
            if (!hash_audio_block(pcm+offset,count,proof.sha256)) {ok=false;break;}
            const auto* raw=reinterpret_cast<const int16_t*>(pcm+offset);
            for (size_t frame=0;frame<proof.frames;++frame)
                for (unsigned slot=0;slot<4;++slot)
                    if (raw[frame*4+slot]==-32768 || raw[frame*4+slot]==32767) ++proof.clipped[slot];
            SpeechBlockResult result;
            const int64_t process_start=esp_timer_get_time();
            bool processed=filter.process(raw,proof.frames,speech+speech_frames,frames/3-speech_frames,result);
            proof.compute_us=esp_timer_get_time()-process_start;
            char after_hash[65]{};
            proof.unchanged=hash_audio_block(pcm+offset,count,after_hash) && strcmp(proof.sha256,after_hash)==0;
            proof.ready_us=esp_timer_get_time();
            if (!processed || !proof.unchanged || result.source_start!=proof.source_start
                    || result.source_frames!=proof.frames) {ok=false;break;}
            speech_frames+=result.output_frames;input_clipped+=result.input_clipped;output_clipped+=result.output_clipped;
            speech_compute_us+=proof.compute_us;++block_count;
        }
        after=audio_ingress_snapshot();
    }
    int64_t ended = esp_timer_get_time();
    bool ingress_ok=ok && after.read_bytes-before.read_bytes==bytes
        && after.dma_bytes-before.dma_bytes>=bytes
        && after.overflows==before.overflows && after.overwritten_bytes==before.overwritten_bytes
        && after.short_reads==before.short_reads && after.read_errors==before.read_errors;
    auto* ingress=diagnostic_event("audio_ingress");
    cJSON_AddStringToObject(ingress,"capture_id",id);
    cJSON_AddNumberToObject(ingress,"requested_bytes",bytes);
    cJSON_AddNumberToObject(ingress,"read_bytes_before",before.read_bytes);
    cJSON_AddNumberToObject(ingress,"read_bytes_after",after.read_bytes);
    cJSON_AddNumberToObject(ingress,"dma_bytes_before",before.dma_bytes);
    cJSON_AddNumberToObject(ingress,"dma_bytes_after",after.dma_bytes);
    cJSON_AddNumberToObject(ingress,"overwritten_bytes_before",before.overwritten_bytes);
    cJSON_AddNumberToObject(ingress,"overwritten_bytes_after",after.overwritten_bytes);
    cJSON_AddNumberToObject(ingress,"overflows_before",before.overflows);
    cJSON_AddNumberToObject(ingress,"overflows_after",after.overflows);
    cJSON_AddNumberToObject(ingress,"short_reads_before",before.short_reads);
    cJSON_AddNumberToObject(ingress,"short_reads_after",after.short_reads);
    cJSON_AddNumberToObject(ingress,"read_errors_before",before.read_errors);
    cJSON_AddNumberToObject(ingress,"read_errors_after",after.read_errors);
    cJSON_AddNumberToObject(ingress,"acquisition_start_us",started);
    cJSON_AddNumberToObject(ingress,"acquisition_end_us",ended);
    diagnostic_emit(ingress);
    diagnostic_check("audio_ingress",ingress_ok ? "pass":"fail",
                     "Exact returned bytes and zero IDF RX queue loss/short reads/errors within this epoch only.");
    if (ok) {
        auto* e = diagnostic_event("capture_start");
        cJSON_AddStringToObject(e, "format", "pcm_s16le");
        cJSON_AddNumberToObject(e, "sample_rate_hz", 48000);
        cJSON_AddNumberToObject(e, "channels", 4);
        cJSON_AddNumberToObject(e, "frames", frames);
        cJSON_AddNumberToObject(e, "gain_db", 24);
        cJSON_AddNumberToObject(e, "acquisition_start_us", started);
        cJSON_AddNumberToObject(e, "acquisition_end_us", ended);
        cJSON_AddStringToObject(e, "channel_mapping", "TDM slots 0-3; physical mapping not yet verified");
        cJSON_AddStringToObject(e, "processing", "none; speaker muted; IDF RX counters recorded for this acquisition epoch");
        cJSON_AddBoolToObject(e,"driver_epoch_integrity",ingress_ok);
        cJSON_AddStringToObject(e,"ingress_boundary","successful codec read, before synchronous speech consumer; capture-relative frames");
        auto* blocks=cJSON_AddArrayToObject(e,"ingress_blocks");
        for (size_t index=0;index<block_count;++index) {
            const auto& proof=proofs[index];
            auto* block=cJSON_CreateObject();
            cJSON_AddNumberToObject(block,"source_start_frame",proof.source_start);
            cJSON_AddNumberToObject(block,"frames",proof.frames);
            cJSON_AddNumberToObject(block,"read_end_us",proof.read_end_us);
            cJSON_AddNumberToObject(block,"speech_ready_us",proof.ready_us);
            cJSON_AddNumberToObject(block,"speech_compute_us",proof.compute_us);
            cJSON_AddStringToObject(block,"sha256",proof.sha256);
            cJSON_AddBoolToObject(block,"raw_unchanged",proof.unchanged);
            auto* clipped=cJSON_AddArrayToObject(block,"clipped_samples");
            for (auto count:proof.clipped) cJSON_AddItemToArray(clipped,cJSON_CreateNumber(count));
            cJSON_AddItemToArray(blocks,block);
        }
        diagnostic_stage("TRICORDER / saving recording\n\nPlease wait for the playback slot labels.");
        ok = export_diagnostic_capture(id, pcm, bytes, e);
        if (ok) {
            char speech_id[80];snprintf(speech_id,sizeof(speech_id),"%s-speech",id);
            auto* derived=diagnostic_event("capture_start");
            cJSON_AddStringToObject(derived,"role","speech_live");
            cJSON_AddStringToObject(derived,"format","pcm_s16le");
            cJSON_AddStringToObject(derived,"source_capture_id",id);
            cJSON_AddNumberToObject(derived,"source_slot",0);
            cJSON_AddNumberToObject(derived,"source_start_frame",0);
            cJSON_AddNumberToObject(derived,"source_frames",frames);
            cJSON_AddNumberToObject(derived,"channels",1);
            cJSON_AddNumberToObject(derived,"sample_rate_hz",16000);
            cJSON_AddNumberToObject(derived,"frames",speech_frames);
            cJSON_AddNumberToObject(derived,"compute_us",speech_compute_us);
            cJSON_AddNumberToObject(derived,"input_clipped",input_clipped);
            cJSON_AddNumberToObject(derived,"output_clipped",output_clipped);
            cJSON_AddStringToObject(derived,"processing","dc80-fir63-fc6500-decimate3-v1");
            ok=speech_frames==frames/3;
            if (ok) ok=export_diagnostic_capture(speech_id,reinterpret_cast<const uint8_t*>(speech),speech_frames*2,derived);
            else cJSON_Delete(derived);
        }
        if (ok && playback) play_slots(speaker, reinterpret_cast<const int16_t*>(pcm), frames, id);
    }
    diagnostic_check("audio_capture", ok ? "pass" : "fail",
                     "Isolated PCM capture/export only; no continuity or acoustic channel-mapping claim.");
    free(speech);free(proofs);free(pcm);
    esp_codec_dev_close(microphone);
    esp_codec_dev_close(speaker);
}
