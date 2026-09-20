#include "audio_workload.h"

bool AudioWorkloadConsumer::process(const int16_t* raw,size_t frames,int16_t* output,size_t capacity,
                                    AudioWorkloadResult& result) {
    if (frames!=480) return false;
    SpeechBlockResult speech;
    if (!speech_.process(raw,frames,output,capacity,speech)) return false;
    result={};result.speech=speech;
    for (size_t frame=0;frame<frames;++frame) {
        rolling_[head_]=raw[frame*4];
        head_=(head_+1)%2048;
    }
    const uint64_t end=speech.source_start+frames;
    if (end%2400!=0) return true;
    for (unsigned frame=0;frame<2048;++frame) fft_input_[frame]=rolling_[(head_+frame)%2048];
    result.fft_start_frame=end-2048;
    result.fft_ready=spectrum_pcm16(fft_input_,2048,1,0,workspace_,amplitudes_,1025,result.spectrum);
    return result.fft_ready;
}
