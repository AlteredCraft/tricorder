#include "audio_devices.h"
#include "workload_metrics.h"
#include "audio_ingress.h"
#include "audio_workload.h"
#include "diagnostic_events.h"
#include "media.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "mbedtls/sha256.h"
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <new>


struct MemorySample {
    size_t internal=0,external=0,largest_internal=0,largest_external=0,stack=0;
};

void run_audio_baseline(const char* boot_id) {
    constexpr size_t blocks=6000,block_frames=480,block_bytes=block_frames*8;
    static unsigned run_number;
    char id[80];snprintf(id,sizeof(id),"%s-audio-baseline-%u",boot_id,run_number++);
    diagnostic_stage("AUDIO BASELINE / 60 seconds\n\nContinuous capture, speech copy and FFT.\nPlease leave the device powered and connected.");
    auto speaker=diagnostic_speaker();auto microphone=diagnostic_microphone();
    auto* raw=static_cast<int16_t*>(heap_caps_malloc(block_bytes,MALLOC_CAP_SPIRAM));
    auto* speech=static_cast<int16_t*>(heap_caps_malloc(160*2,MALLOC_CAP_SPIRAM));
    auto* timings=static_cast<uint32_t*>(heap_caps_malloc(blocks*4*sizeof(uint32_t),MALLOC_CAP_SPIRAM));
    void* space=heap_caps_aligned_alloc(16,sizeof(AudioWorkloadConsumer),MALLOC_CAP_SPIRAM);
    auto* consumer=space ? new(space) AudioWorkloadConsumer():nullptr;
    auto* memory=static_cast<MemorySample*>(calloc(60,sizeof(MemorySample)));
    bool ok=speaker && microphone && raw && speech && timings && consumer && memory;
    esp_codec_dev_sample_info_t input{};input.sample_rate=48000;input.channel=4;input.bits_per_sample=16;
    auto output=input;output.channel=2;
    if (ok) ok=esp_codec_dev_open(microphone,&input)==ESP_OK && esp_codec_dev_open(speaker,&output)==ESP_OK
        && esp_codec_dev_set_out_mute(speaker,true)==ESP_OK && esp_codec_dev_set_in_gain(microphone,24)==ESP_OK;
    auto* cpu_before=workload_cpu_snapshot();
    AudioIngressSnapshot before{},after{};
    size_t completed=0,speech_frames=0,fft_count=0,mutations=0;
    int64_t started=esp_timer_get_time();
    if (ok) ok=begin_audio_epoch(before);
    for (size_t block=0;ok && block<blocks;++block) {
        if (esp_codec_dev_read(microphone,raw,block_bytes)!=ESP_OK) {ok=false;break;}
        int64_t read_end=esp_timer_get_time();
        unsigned char original[32],final[32];
        if (mbedtls_sha256(reinterpret_cast<const uint8_t*>(raw),block_bytes,original,0)) {ok=false;break;}
        AudioWorkloadResult result;
        int64_t compute_start=esp_timer_get_time();
        bool processed=consumer->process(raw,block_frames,speech,160,result);
        int64_t compute=esp_timer_get_time()-compute_start;
        if (mbedtls_sha256(reinterpret_cast<const uint8_t*>(raw),block_bytes,final,0)) {ok=false;break;}
        if (memcmp(original,final,32)) ++mutations;
        const int64_t ready=esp_timer_get_time();
        ok=processed && result.speech.source_start==block*block_frames && result.speech.output_frames==160;
        if (ready-started>65000000) ok=false; // Bounded failed run if the source stalls.
        if (!ok) break;
        timings[block*4]=read_end-started;timings[block*4+1]=ready-started;
        timings[block*4+2]=compute;timings[block*4+3]=result.fft_ready;
        speech_frames+=result.speech.output_frames;fft_count+=result.fft_ready;++completed;
        if (completed%100==0) {
            auto& sample=memory[completed/100-1];
            sample.internal=heap_caps_get_free_size(MALLOC_CAP_INTERNAL);
            sample.external=heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
            sample.largest_internal=heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL);
            sample.largest_external=heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM);
            sample.stack=uxTaskGetStackHighWaterMark(nullptr);
        }
    }
    after=audio_ingress_snapshot();
    const int64_t ended=esp_timer_get_time();
    auto* cpu_after=workload_cpu_snapshot();
    if (microphone) esp_codec_dev_close(microphone);
    if (speaker) esp_codec_dev_close(speaker);
    auto* meta=diagnostic_event("capture_start");
    cJSON_AddStringToObject(meta,"format","audio_baseline_u32le");
    cJSON_AddStringToObject(meta,"layout","read_end_us,consumer_ready_us,consumer_compute_us,fft_ready; times relative to acquisition start");
    cJSON_AddNumberToObject(meta,"rows",completed);cJSON_AddNumberToObject(meta,"columns",4);
    cJSON_AddNumberToObject(meta,"sample_rate_hz",48000);cJSON_AddNumberToObject(meta,"raw_channels",4);
    cJSON_AddNumberToObject(meta,"source_slot",0);cJSON_AddNumberToObject(meta,"gain_db_requested",24);
    cJSON_AddNumberToObject(meta,"block_frames",block_frames);cJSON_AddNumberToObject(meta,"raw_frames",completed*block_frames);
    cJSON_AddNumberToObject(meta,"speech_rate_hz",16000);cJSON_AddNumberToObject(meta,"speech_frames",speech_frames);
    cJSON_AddNumberToObject(meta,"fft_frames",2048);cJSON_AddNumberToObject(meta,"fft_hop_frames",2400);
    cJSON_AddNumberToObject(meta,"fft_count",fft_count);cJSON_AddNumberToObject(meta,"raw_mutations",mutations);
    cJSON_AddNumberToObject(meta,"duration_us",ended-started);
    cJSON_AddNumberToObject(meta,"acquisition_start_us",started);cJSON_AddNumberToObject(meta,"acquisition_end_us",ended);
#define DELTA(field) cJSON_AddNumberToObject(meta,#field,after.field-before.field)
    DELTA(read_bytes);DELTA(dma_bytes);DELTA(overwritten_bytes);DELTA(overflows);DELTA(short_reads);DELTA(read_errors);
#undef DELTA
    cJSON_AddNumberToObject(meta,"lifetime_min_internal",heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL));
    cJSON_AddNumberToObject(meta,"lifetime_min_psram",heap_caps_get_minimum_free_size(MALLOC_CAP_SPIRAM));
    auto* samples=cJSON_AddArrayToObject(meta,"memory_samples");
    for (size_t index=0;memory && index<completed/100;++index) {
        auto* sample=cJSON_CreateObject();const auto& saved=memory[index];
        cJSON_AddNumberToObject(sample,"block_index",(index+1)*100);
        cJSON_AddNumberToObject(sample,"free_internal",saved.internal);cJSON_AddNumberToObject(sample,"free_psram",saved.external);
        cJSON_AddNumberToObject(sample,"largest_internal",saved.largest_internal);cJSON_AddNumberToObject(sample,"largest_psram",saved.largest_external);
        cJSON_AddNumberToObject(sample,"stack_margin_bytes",saved.stack);cJSON_AddItemToArray(samples,sample);
    }
    if (cpu_before) cJSON_AddItemToObject(meta,"cpu_before",cpu_before);
    if (cpu_after) cJSON_AddItemToObject(meta,"cpu_after",cpu_after);
    bool exported=completed && export_diagnostic_capture(id,reinterpret_cast<const uint8_t*>(timings),completed*16,meta);
    if (!completed) cJSON_Delete(meta);
    ok=ok && exported && completed==blocks && speech_frames==960000 && fft_count==1200 && mutations==0
        && after.read_bytes-before.read_bytes==blocks*block_bytes && after.dma_bytes-before.dma_bytes>=blocks*block_bytes
        && after.overflows==before.overflows && after.overwritten_bytes==before.overwritten_bytes
        && after.short_reads==before.short_reads && after.read_errors==before.read_errors;
    if (consumer) consumer->~AudioWorkloadConsumer();
    free(space);free(memory);free(raw);free(speech);free(timings);
    diagnostic_check("audio_baseline",ok ? "pass":"fail","60-second isolated audio/speech/FFT counters; host timing/memory assessment required.");
}
