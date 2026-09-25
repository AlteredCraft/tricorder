#pragma once
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>

// Comparison level: median power of 100 ms (4800-frame) windows of one slot,
// in dBFS, so brief loud moments don't swing it. A capture shorter than one
// window is one window; frames past the last full window are ignored. Two
// middle windows are averaged in power. NAN when that median power is 0.
// The host computes the same value independently (tools/investigation.py).
inline double median_window_dbfs(const int16_t* pcm,size_t frames,unsigned channels,unsigned slot) {
    constexpr size_t max_windows=64;
    if(!pcm || !frames || slot>=channels)return NAN;
    const size_t windows=std::min(max_windows,std::max<size_t>(1,frames/4800)),length=frames/windows;
    double power[max_windows];
    for(size_t w=0;w<windows;++w) {
        uint64_t sum=0;
        for(size_t i=w*length;i<(w+1)*length;++i) {const int64_t v=pcm[i*channels+slot];sum+=v*v;}
        power[w]=static_cast<double>(sum)/length;
    }
    std::sort(power,power+windows);
    const double median=windows%2?power[windows/2]:(power[windows/2-1]+power[windows/2])/2;
    return median>0?10*std::log10(median/(32768.0*32768.0)):NAN;
}
