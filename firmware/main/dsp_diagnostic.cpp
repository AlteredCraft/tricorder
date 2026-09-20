#include "dsp_diagnostic.h"
#include "dsp_fixtures.generated.h"
#include "spectrum.h"
#include "media.h"
#include "diagnostic_events.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "mbedtls/sha256.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>

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
