#include "investigation_capture.h"
#include "audio_devices.h"
#include "audio_ingress.h"
#include "diagnostic_events.h"
#include "spectrum_display.h"
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
cJSON* counters(const AudioIngressSnapshot& s) {
    auto* o=cJSON_CreateObject();
    cJSON_AddNumberToObject(o,"dma_bytes",s.dma_bytes);cJSON_AddNumberToObject(o,"read_bytes",s.read_bytes);
    cJSON_AddNumberToObject(o,"overflows",s.overflows);cJSON_AddNumberToObject(o,"overwritten_bytes",s.overwritten_bytes);
    cJSON_AddNumberToObject(o,"short_reads",s.short_reads);cJSON_AddNumberToObject(o,"read_errors",s.read_errors);
    return o;
}
}
InvestigationCapture::~InvestigationCapture(){free(bytes);cJSON_Delete(metadata);cJSON_Delete(measurement);}
bool investigation_capture(const char* boot,const char* session,const char* id,
                           const std::atomic<bool>& cancel,InvestigationCapture& out,
                           CaptureSpectrumTap tap) {
    constexpr size_t frames=144000,bytes=frames*8,block_bytes=8192,warmup_frames=24000;
    if(out.bytes || out.metadata || out.measurement)return false;
    out.bytes=static_cast<unsigned char*>(heap_caps_malloc(bytes,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
    out.metadata=cJSON_CreateObject();out.measurement=cJSON_CreateObject();
    if(!out.bytes || !out.metadata || !out.measurement)return false;
    auto* blocks=cJSON_AddArrayToObject(out.metadata,"ingress_blocks");
    // Allocate proofs before starting RX, then serialize after stopping it.
    struct Proof {uint64_t read_us;char sha[65];};
    auto* proofs=static_cast<Proof*>(heap_caps_calloc((bytes+block_bytes-1)/block_bytes,sizeof(Proof),MALLOC_CAP_SPIRAM));
    if(!proofs)return false;
    struct LiveView {SpectrumWorkspace workspace;float amplitudes[spectrum_max_frames/2+1];};
    std::unique_ptr<LiveView,decltype(&free)> live(tap?static_cast<LiveView*>(
        heap_caps_aligned_alloc(16,sizeof(LiveView),MALLOC_CAP_SPIRAM)):nullptr,free);
    unsigned live_views=0;uint64_t live_max_us=0;
    auto mic=diagnostic_microphone();auto speaker=diagnostic_speaker();
    esp_codec_dev_sample_info_t input{};input.sample_rate=48000;input.channel=4;input.bits_per_sample=16;
    auto output=input;output.channel=2;
    bool mic_open=mic && esp_codec_dev_open(mic,&input)==ESP_OK;
    bool speaker_open=speaker && esp_codec_dev_open(speaker,&output)==ESP_OK;
    bool ok=mic_open && speaker_open && esp_codec_dev_set_out_mute(speaker,true)==ESP_OK &&
        esp_codec_dev_set_in_gain(mic,24)==ESP_OK && !cancel.load();
    AudioIngressSnapshot before{},after{};
    uint64_t epoch_start=esp_timer_get_time();
    if(ok)ok=begin_audio_epoch(before);
    // The real first trial contains codec startup transients for ~0.2 seconds.
    // Drain an explicit 0.5-second settling prefix before the measurement starts.
    // Keep RX continuous: restarting it here could reintroduce clock transients.
    // These samples are not measurement data; their count stays in the epoch
    // proof so no driver loss can be hidden by moving the measurement boundary.
    for(size_t offset=0;ok && offset<warmup_frames*8;offset+=block_bytes) {
        const size_t n=std::min(block_bytes,warmup_frames*8-offset);
        ok=!cancel.load() && esp_codec_dev_read(mic,out.bytes,n)==ESP_OK;
    }
    uint64_t start=esp_timer_get_time();
    uint64_t squared=0;unsigned peak=0,clipped=0;size_t count=0;
    for(size_t offset=0;ok && offset<bytes;offset+=block_bytes) {
        size_t n=std::min(block_bytes,bytes-offset);
        if(cancel.load() || esp_codec_dev_read(mic,out.bytes+offset,n)!=ESP_OK){ok=false;break;}
        proofs[count].read_us=esp_timer_get_time();
        ok=hash(out.bytes+offset,n,proofs[count].sha);
        const auto* pcm=reinterpret_cast<const int16_t*>(out.bytes+offset);
        for(size_t i=0;i<n/8;++i) {
            int v=pcm[i*4];squared+=static_cast<int64_t>(v)*v;
            peak=std::max(peak,static_cast<unsigned>(std::abs(v)));clipped+=v==-32768 || v==32767;
        }
        ++count;
        if(ok && live && count%4==0 && offset+n>=spectrum_max_frames*8) {
            const uint64_t started=esp_timer_get_time();SpectrumResult result;SpectrumBands bands;float db[spectrum_band_count];
            const auto* window=reinterpret_cast<const int16_t*>(out.bytes+offset+n)-spectrum_max_frames*4;
            if(spectrum_pcm16(window,spectrum_max_frames,4,0,live->workspace,live->amplitudes,
                              spectrum_max_frames/2+1,result) &&
               spectrum_bands_add(live->amplitudes,spectrum_max_frames,48000,bands)) {
                spectrum_bands_db(bands,db);tap(db);++live_views;
            }
            live_max_us=std::max(live_max_us,esp_timer_get_time()-started);
        }
    }
    after=audio_ingress_snapshot();uint64_t end=esp_timer_get_time();
    // RX must be stopped before any network or JSON work; never upload while
    // the bounded capture is still being filled.
    if(mic_open && esp_codec_dev_close(mic)!=ESP_OK)ok=false;
    if(speaker_open && esp_codec_dev_close(speaker)!=ESP_OK)ok=false;
    ok=ok && !cancel.load() && after.read_bytes-before.read_bytes==bytes+warmup_frames*8 && after.dma_bytes-before.dma_bytes>=bytes+warmup_frames*8 &&
        after.overflows==before.overflows && after.overwritten_bytes==before.overwritten_bytes &&
        after.short_reads==before.short_reads && after.read_errors==before.read_errors;
    for(size_t i=0;ok && i<count;++i) {
        size_t offset=i*block_bytes,n=std::min(block_bytes,bytes-offset);char check[65];
        ok=hash(out.bytes+offset,n,check) && !strcmp(check,proofs[i].sha);
        auto* b=cJSON_CreateObject();cJSON_AddNumberToObject(b,"source_start_frame",offset/8);
        cJSON_AddNumberToObject(b,"frames",n/8);cJSON_AddNumberToObject(b,"read_end_us",proofs[i].read_us);
        cJSON_AddStringToObject(b,"sha256",proofs[i].sha);cJSON_AddItemToArray(blocks,b);
    }
    free(proofs);
    if(live) {
        auto* e=diagnostic_event("investigation_live_spectrum");cJSON_AddStringToObject(e,"capture_id",id);
        cJSON_AddNumberToObject(e,"views",live_views);cJSON_AddNumberToObject(e,"max_us",live_max_us);diagnostic_emit(e);
    }
    if(!ok)return false;
    char digest[65];if(!hash(out.bytes,bytes,digest))return false;
    out.size=bytes;auto* m=out.metadata;
    cJSON_AddStringToObject(m,"boot_id",boot);cJSON_AddStringToObject(m,"session_id",session);
    cJSON_AddStringToObject(m,"capture_id",id);cJSON_AddStringToObject(m,"format","pcm_s16le");
    cJSON_AddStringToObject(m,"sha256",digest);cJSON_AddNumberToObject(m,"size_bytes",bytes);
    cJSON_AddNumberToObject(m,"sample_rate_hz",48000);cJSON_AddNumberToObject(m,"channels",4);
    cJSON_AddNumberToObject(m,"frames",frames);cJSON_AddNumberToObject(m,"gain_db",24);
    cJSON_AddNumberToObject(m,"source_slot",0);cJSON_AddStringToObject(m,"physical_slot","farther-hole");
    cJSON_AddBoolToObject(m,"speaker_active",false);cJSON_AddBoolToObject(m,"driver_epoch_integrity",true);
    cJSON_AddNumberToObject(m,"warmup_frames",warmup_frames);cJSON_AddNumberToObject(m,"epoch_start_us",epoch_start);
    cJSON_AddNumberToObject(m,"acquisition_start_us",start);cJSON_AddNumberToObject(m,"acquisition_end_us",end);
    cJSON_AddItemToObject(m,"ingress_before",counters(before));cJSON_AddItemToObject(m,"ingress_after",counters(after));
    double rms=sqrt(static_cast<double>(squared)/frames);auto* v=out.measurement;
    cJSON_AddNumberToObject(v,"frames",frames);cJSON_AddNumberToObject(v,"rms_counts",rms);
    cJSON_AddNumberToObject(v,"peak_counts",peak);cJSON_AddNumberToObject(v,"clipped_samples",clipped);
    if(rms)cJSON_AddNumberToObject(v,"rms_dbfs",20*log10(rms/32768));else cJSON_AddNullToObject(v,"rms_dbfs");
    return true;
}
bool investigation_record_question(const char* boot,const char* session,const char* id,
                                   const std::atomic<bool>& cancel,const std::atomic<bool>& stop,
                                   InvestigationCapture& out,QuestionLevelTap level) {
    // 8 s of 48 kHz source -> 128000 frames of 16 kHz mono (256000 bytes).
    constexpr size_t source_limit=384000,block_frames=1024,block_bytes=block_frames*8,warmup_frames=12000;
    constexpr size_t capacity=source_limit/3;
    if(out.bytes || out.metadata || out.measurement)return false;
    out.bytes=static_cast<unsigned char*>(heap_caps_malloc(capacity*2,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
    std::unique_ptr<int16_t,decltype(&free)> block(static_cast<int16_t*>(
        heap_caps_malloc(block_bytes,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT)),free);
    out.metadata=cJSON_CreateObject();
    if(!out.bytes || !block || !out.metadata)return false;
    auto mic=diagnostic_microphone();auto speaker=diagnostic_speaker();
    esp_codec_dev_sample_info_t input{};input.sample_rate=48000;input.channel=4;input.bits_per_sample=16;
    auto output=input;output.channel=2;
    bool mic_open=mic && esp_codec_dev_open(mic,&input)==ESP_OK;
    bool speaker_open=speaker && esp_codec_dev_open(speaker,&output)==ESP_OK;
    bool ok=mic_open && speaker_open && esp_codec_dev_set_out_mute(speaker,true)==ESP_OK &&
        esp_codec_dev_set_in_gain(mic,24)==ESP_OK && !cancel.load();
    AudioIngressSnapshot before{},after{};
    if(ok)ok=begin_audio_epoch(before);
    // Same codec settling as measurements, shortened so the first word is kept.
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
    if(mic_open && esp_codec_dev_close(mic)!=ESP_OK)ok=false;
    if(speaker_open && esp_codec_dev_close(speaker)!=ESP_OK)ok=false;
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
