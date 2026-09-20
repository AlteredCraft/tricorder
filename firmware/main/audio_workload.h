#pragma once
#include "speech_filter.h"
#include "spectrum.h"

struct AudioWorkloadResult {
    SpeechBlockResult speech;
    SpectrumResult spectrum;
    uint64_t fft_start_frame=0;
    bool fft_ready=false;
};

// Synchronous bounded consumer. Copies the selected raw slot into its own
// rolling window; never retains the producer's buffer. One caller owns it.
class AudioWorkloadConsumer {
public:
    bool process(const int16_t* raw,size_t frames,int16_t* speech,size_t capacity,AudioWorkloadResult& result);
private:
    SpeechFilter speech_{true,4,0};
    int16_t rolling_[2048]{},fft_input_[2048]{};
    unsigned head_=0;
    SpectrumWorkspace workspace_{};
    float amplitudes_[1025]{};
};
