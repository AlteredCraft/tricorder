#include "dsp_diagnostic.h"
#include "dsp_fixtures.generated.h"
#include "spectrum.h"
#include "speech_filter.h"
#include "media.h"
#include "diagnostic_events.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "mbedtls/sha256.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <algorithm>

static bool hash_pcm(const int16_t* data, size_t frames, char* output) {
    unsigned char digest[32];
    if (mbedtls_sha256(reinterpret_cast<const unsigned char*>(data),frames*2,digest,0)) return false;
    for (size_t i=0;i<32;++i) snprintf(output+i*2,3,"%02x",digest[i]);
    return true;
}

void run_dsp_fixtures(const char* boot_id) {
    diagnostic_stage("Checking synthetic FFT fixtures...");
    auto* workspace=static_cast<SpectrumWorkspace*>(heap_caps_aligned_alloc(16,sizeof(SpectrumWorkspace),MALLOC_CAP_SPIRAM));
    auto* input=static_cast<int16_t*>(heap_caps_malloc(2048*2,MALLOC_CAP_SPIRAM));
    auto* output=static_cast<float*>(heap_caps_malloc(1025*sizeof(float),MALLOC_CAP_SPIRAM));
    bool ok=workspace && input && output;
    for (unsigned repetition=1;repetition<=3 && ok;++repetition) {
        for (const auto& fixture:dsp_fixtures) {
            memcpy(input,fixture.pcm,fixture.frames*2);
            char before[65]{},after[65]{};
            if (!hash_pcm(input,fixture.frames,before)) { ok=false;break; }
            SpectrumResult result;
            int64_t start=esp_timer_get_time();
            bool computed=spectrum_pcm16(input,fixture.frames,1,0,*workspace,output,1025,result);
            int64_t duration=esp_timer_get_time()-start;
            if (!computed || !hash_pcm(input,fixture.frames,after)) { ok=false;break; }
            char id[112];
            snprintf(id,sizeof(id),"%s-fft-%u-%s",boot_id,repetition,fixture.name);
            auto* metadata=diagnostic_event("capture_start");
            cJSON_AddStringToObject(metadata,"format","spectrum_f32le");
            cJSON_AddStringToObject(metadata,"fixture_id",fixture.name);
            cJSON_AddNumberToObject(metadata,"repetition",repetition);
            cJSON_AddNumberToObject(metadata,"frames",fixture.frames);
            cJSON_AddNumberToObject(metadata,"sample_rate_hz",48000);
            cJSON_AddStringToObject(metadata,"window","periodic Hann");
            cJSON_AddStringToObject(metadata,"normalization","one-sided amplitude / sum(window); DC and Nyquist undoubled");
            cJSON_AddStringToObject(metadata,"pcm_scale","signed PCM16 / 32768");
            cJSON_AddStringToObject(metadata,"input_sha256_before",before);
            cJSON_AddStringToObject(metadata,"input_sha256_after",after);
            cJSON_AddNumberToObject(metadata,"compute_us",duration);
            cJSON_AddNumberToObject(metadata,"peak_bin",result.peak_bin);
            cJSON_AddNumberToObject(metadata,"peak_amplitude_fs",result.peak_amplitude_fs);
            cJSON_AddNumberToObject(metadata,"clipped_samples",result.clipped_samples);
            ok=export_diagnostic_capture(id,reinterpret_cast<const unsigned char*>(output),1025*sizeof(float),metadata)
                && strcmp(before,after)==0;
            if (!ok) break;
        }
    }
    free(output);free(input);free(workspace);
    diagnostic_check("dsp_fixture_export",ok ? "pass":"fail",
                     "Synthetic kernel execution/export only; independent host comparison required.");
}

void run_speech_fixtures(const char* boot_id) {
    diagnostic_stage("Checking raw / speech separation...");
    auto* input=static_cast<int16_t*>(heap_caps_malloc(2048*2,MALLOC_CAP_SPIRAM));
    auto* output=static_cast<int16_t*>(heap_caps_malloc(2048*2,MALLOC_CAP_SPIRAM));
    bool ok=input && output;
    for (unsigned repetition=1;repetition<=3 && ok;++repetition) {
        for (unsigned mode=0;mode<2 && ok;++mode) {
            for (const auto& fixture:dsp_fixtures) {
                memcpy(input,fixture.pcm,fixture.frames*2);
                char before[65]{},after[65]{};
                if (!hash_pcm(input,fixture.frames,before)) {ok=false;break;}
                SpeechFilter filter(mode!=0,1,0);
                auto* blocks=cJSON_CreateArray();
                size_t produced=0,input_clipped=0,output_clipped=0;
                int64_t compute_us=0;
                for (size_t offset=0;offset<fixture.frames;offset+=480) {
                    size_t count=std::min(size_t(480),fixture.frames-offset);
                    char digest[65]{};
                    if (!hash_pcm(input+offset,count,digest)) {ok=false;break;}
                    auto* block=cJSON_CreateObject();
                    cJSON_AddNumberToObject(block,"source_start_frame",offset);
                    cJSON_AddNumberToObject(block,"frames",count);
                    cJSON_AddStringToObject(block,"sha256",digest);
                    cJSON_AddItemToArray(blocks,block);
                    SpeechBlockResult result;
                    int64_t started=esp_timer_get_time();
                    bool processed=filter.process(input+offset,count,output+produced,2048-produced,result);
                    compute_us+=esp_timer_get_time()-started;
                    if (!processed || result.source_start!=offset || result.source_frames!=count) {ok=false;break;}
                    produced+=result.output_frames;input_clipped+=result.input_clipped;output_clipped+=result.output_clipped;
                }
                if (!ok || !hash_pcm(input,fixture.frames,after)) {cJSON_Delete(blocks);ok=false;break;}
                char raw_id[96],speech_id[96];
                snprintf(raw_id,sizeof(raw_id),"%s-sp-%u-%u-%s-raw",boot_id,repetition,mode,fixture.name);
                snprintf(speech_id,sizeof(speech_id),"%s-sp-%u-%u-%s-out",boot_id,repetition,mode,fixture.name);
                auto metadata=[&](const char* role,size_t frames,unsigned rate) {
                    auto* item=diagnostic_event("capture_start");
                    cJSON_AddStringToObject(item,"format","pcm_s16le");
                    cJSON_AddStringToObject(item,"role",role);
                    cJSON_AddStringToObject(item,"fixture_id",fixture.name);
                    cJSON_AddNumberToObject(item,"repetition",repetition);
                    cJSON_AddBoolToObject(item,"speech_enabled",mode!=0);
                    cJSON_AddNumberToObject(item,"frames",frames);
                    cJSON_AddNumberToObject(item,"channels",1);
                    cJSON_AddNumberToObject(item,"sample_rate_hz",rate);
                    return item;
                };
                auto* raw=metadata("measurement_replay",fixture.frames,48000);
                cJSON_AddStringToObject(raw,"input_sha256_before",before);
                cJSON_AddStringToObject(raw,"input_sha256_after",after);
                cJSON_AddItemToObject(raw,"ingress_blocks",blocks);
                ok=export_diagnostic_capture(raw_id,reinterpret_cast<const unsigned char*>(input),fixture.frames*2,raw)
                    && strcmp(before,after)==0;
                if (!ok) break;
                auto* speech=metadata("speech_replay",produced,mode ? 16000:48000);
                cJSON_AddStringToObject(speech,"source_capture_id",raw_id);
                cJSON_AddNumberToObject(speech,"source_start_frame",0);
                cJSON_AddNumberToObject(speech,"source_frames",fixture.frames);
                cJSON_AddNumberToObject(speech,"compute_us",compute_us);
                cJSON_AddNumberToObject(speech,"input_clipped",input_clipped);
                cJSON_AddNumberToObject(speech,"output_clipped",output_clipped);
                cJSON_AddStringToObject(speech,"processing",mode ? "dc80-fir63-fc6500-decimate3-v1":"selected-slot-copy-v1");
                ok=export_diagnostic_capture(speech_id,reinterpret_cast<const unsigned char*>(output),produced*2,speech);
                if (!ok) break;
            }
        }
    }
    free(output);free(input);
    diagnostic_check("speech_fixture_export",ok ? "pass":"fail",
                     "Synchronous synthetic raw/speech exports; host reference and ingress hash comparison required.");
}
