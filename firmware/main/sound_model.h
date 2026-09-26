#pragma once
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
// Sound instrument (F-0001 T2): display-only level, peak hold and the sliding
// FFT window. Host-testable; the measurement path stays in investigation_capture.
namespace sound {
constexpr float level_floor_db=-100;
// RMS of one slot of interleaved PCM16, in dB relative to full scale (32767).
inline float level_dbfs(const int16_t* pcm,size_t frames,unsigned channels,unsigned slot) {
    double squared=0;
    for(size_t i=0;i<frames;++i){const double v=pcm[i*channels+slot];squared+=v*v;}
    if(!frames || squared<=0)return level_floor_db;
    const float db=10.0f*std::log10(static_cast<float>(squared/frames))-20.0f*std::log10(32767.0f);
    return db<level_floor_db?level_floor_db:db;
}
inline void reset_peak(float* peak,size_t bands) {for(size_t i=0;i<bands;++i)peak[i]=-1000;}
inline void hold_peak(const float* db,float* peak,size_t bands) {
    for(size_t i=0;i<bands;++i)if(db[i]>peak[i])peak[i]=db[i];
}
// The newest Frames interleaved frames, oldest first after copy(). Blocks may be
// any size; a block larger than the window keeps only its tail.
template<size_t Frames,unsigned Channels>
struct Window {
    int16_t ring[Frames*Channels]{};
    size_t next=0,filled=0;
    void push(const int16_t* pcm,size_t frames) {
        if(frames>Frames){pcm+=(frames-Frames)*Channels;frames=Frames;}
        for(size_t i=0;i<frames;++i){
            memcpy(ring+next*Channels,pcm+i*Channels,Channels*sizeof(int16_t));next=(next+1)%Frames;
        }
        filled=filled+frames>Frames?Frames:filled+frames;
    }
    bool full() const {return filled==Frames;}
    void copy(int16_t* out) const {
        const size_t tail=Frames-next;
        memcpy(out,ring+next*Channels,tail*Channels*sizeof(int16_t));
        memcpy(out+tail*Channels,ring,next*Channels*sizeof(int16_t));
    }
};
}
