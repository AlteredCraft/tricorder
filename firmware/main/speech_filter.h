#pragma once
#include <cstddef>
#include <cstdint>

struct SpeechBlockResult {
    uint64_t source_start=0;
    size_t source_frames=0,output_frames=0,input_clipped=0,output_clipped=0;
};

// One synchronous consumer. History contains copied samples, never raw pointers.
// Source is const; destination must be separately owned and non-overlapping.
class SpeechFilter {
public:
    SpeechFilter(bool enabled,unsigned channels,unsigned slot)
        : enabled_(enabled),channels_(channels),slot_(slot) {}
    bool process(const int16_t* source,size_t frames,int16_t* output,size_t capacity,SpeechBlockResult& result);
private:
    bool enabled_;
    unsigned channels_,slot_;
    uint64_t source_frames_=0;
    float history_[63]{},previous_input_=0,previous_highpass_=0;
    unsigned head_=0,phase_=0;
};
