#include "voice_note.h"
#include "audio_devices.h"
#include "audio_ingress.h"
#include "speech_filter.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "mbedtls/sha256.h"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>

namespace {
bool hash(const void* data,size_t size,char out[65]) {
    unsigned char digest[32];
    if(mbedtls_sha256(static_cast<const unsigned char*>(data),size,digest,0))return false;
    for(unsigned i=0;i<32;++i)snprintf(out+2*i,3,"%02x",digest[i]);
    return true;
}
}
VoiceNote::~VoiceNote(){free(bytes);cJSON_Delete(metadata);}
bool voice_note_record(const char* boot,const char* session,const char* id,
                       const std::atomic<bool>& cancel,const std::atomic<bool>& stop,
                       VoiceNote& out,VoiceLevelTap level) {
    // 8 s of 48 kHz source -> 128000 frames of 16 kHz mono (256000 bytes).
    constexpr size_t source_limit=384000,block_frames=1024,block_bytes=block_frames*8,warmup_frames=12000;
    constexpr size_t capacity=source_limit/3;
    if(out.bytes || out.metadata)return false;
    out.bytes=static_cast<unsigned char*>(heap_caps_malloc(capacity*2,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
    std::unique_ptr<int16_t,decltype(&free)> block(static_cast<int16_t*>(
        heap_caps_malloc(block_bytes,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT)),free);
    out.metadata=cJSON_CreateObject();
    if(!out.bytes || !block || !out.metadata)return false;
    auto mic=diagnostic_microphone();auto speaker=diagnostic_speaker();
    esp_codec_dev_sample_info_t input{};input.sample_rate=48000;input.channel=4;input.bits_per_sample=16;
    auto output=input;output.channel=2;
    const bool mic_open=mic && esp_codec_dev_open(mic,&input)==ESP_OK;
    const bool speaker_open=speaker && esp_codec_dev_open(speaker,&output)==ESP_OK;
    bool ok=mic_open && speaker_open && esp_codec_dev_set_out_mute(speaker,true)==ESP_OK &&
        esp_codec_dev_set_in_gain(mic,24)==ESP_OK && !cancel.load();
    AudioIngressSnapshot before{},after{};
    if(ok)ok=begin_audio_epoch(before);
    // Let the codec settle, briefly, so the first word is kept.
    for(size_t offset=0;ok && offset<warmup_frames*8;offset+=block_bytes) {
        const size_t n=std::min(block_bytes,warmup_frames*8-offset);
        ok=!cancel.load() && esp_codec_dev_read(mic,block.get(),n)==ESP_OK;
    }
    SpeechFilter filter(true,4,0);
    auto* pcm=reinterpret_cast<int16_t*>(out.bytes);
    size_t source=0,frames=0,clipped=0;bool limit=false;
    const uint64_t start=esp_timer_get_time();
    while(ok) {
        if(cancel.load() || esp_codec_dev_read(mic,block.get(),block_bytes)!=ESP_OK){ok=false;break;}
        SpeechBlockResult r;
        ok=filter.process(block.get(),block_frames,pcm+frames,capacity-frames,r);
        if(!ok)break;
        if(level) {
            double energy=0;for(size_t i=0;i<r.output_frames;++i)energy+=double(pcm[frames+i])*pcm[frames+i];
            const double rms=r.output_frames?std::sqrt(energy/r.output_frames):0;
            level(rms>0?static_cast<float>(20*std::log10(rms/32768)):-120.0f);
        }
        frames+=r.output_frames;clipped+=r.input_clipped;source+=block_frames;
        if(source>=source_limit){limit=true;break;}
        if(stop.load())break;
    }
    after=audio_ingress_snapshot();const uint64_t end=esp_timer_get_time();
    // Close even after a failed open: esp_codec_dev marks a device open before
    // configuring it, and a later open of a marked device skips configuration.
    if(mic && esp_codec_dev_close(mic)!=ESP_OK)ok=false;
    if(speaker && esp_codec_dev_close(speaker)!=ESP_OK)ok=false;
    const size_t read=(source+warmup_frames)*8;
    ok=ok && !cancel.load() && frames && after.read_bytes-before.read_bytes==read &&
        after.dma_bytes-before.dma_bytes>=read && after.overflows==before.overflows &&
        after.overwritten_bytes==before.overwritten_bytes && after.short_reads==before.short_reads &&
        after.read_errors==before.read_errors;
    char digest[65];
    if(!ok || !hash(out.bytes,frames*2,digest))return false;
    out.size=frames*2;auto* m=out.metadata;
    cJSON_AddStringToObject(m,"question_id",id);cJSON_AddStringToObject(m,"boot_id",boot);
    cJSON_AddStringToObject(m,"session_id",session);cJSON_AddStringToObject(m,"format","pcm_s16le");
    cJSON_AddNumberToObject(m,"sample_rate_hz",16000);cJSON_AddNumberToObject(m,"channels",1);
    cJSON_AddNumberToObject(m,"frames",frames);cJSON_AddNumberToObject(m,"size_bytes",frames*2);
    cJSON_AddStringToObject(m,"sha256",digest);cJSON_AddNumberToObject(m,"source_rate_hz",48000);
    cJSON_AddNumberToObject(m,"source_slot",0);cJSON_AddNumberToObject(m,"gain_db",24);
    cJSON_AddStringToObject(m,"filter","hpf80-lpf6500-63tap-decimate3");
    cJSON_AddNumberToObject(m,"warmup_frames",warmup_frames);
    cJSON_AddNumberToObject(m,"acquisition_start_us",start);cJSON_AddNumberToObject(m,"acquisition_end_us",end);
    cJSON_AddStringToObject(m,"stopped_by",limit?"limit":"operator");
    cJSON_AddNumberToObject(m,"input_clipped",clipped);cJSON_AddBoolToObject(m,"driver_epoch_integrity",true);
    return true;
}
