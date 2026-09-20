#include "spectrum.h"
#include <algorithm>
#include <cmath>

static bool overlaps(const void* a, size_t a_size, const void* b, size_t b_size) {
    auto first = reinterpret_cast<uintptr_t>(a);
    auto second = reinterpret_cast<uintptr_t>(b);
    return first < second+b_size && second < first+a_size;
}

bool spectrum_pcm16(const int16_t* input, size_t frames, unsigned channels,
                    unsigned slot, SpectrumWorkspace& workspace,
                    float* amplitudes, size_t amplitude_capacity, SpectrumResult& result) {
    if (!input || !amplitudes || frames<8 || frames>spectrum_max_frames
        || (frames & (frames-1)) || channels<1 || channels>4 || slot>=channels
        || amplitude_capacity<frames/2+1) return false;
    size_t input_bytes=frames*channels*sizeof(int16_t);
    size_t output_bytes=(frames/2+1)*sizeof(float);
    if (overlaps(input,input_bytes,&workspace,sizeof(workspace))
        || overlaps(input,input_bytes,amplitudes,output_bytes)
        || overlaps(&workspace,sizeof(workspace),amplitudes,output_bytes)) return false;
    result = {};
    constexpr float pi=3.14159265358979323846f;
    double window_sum=0;
    for (size_t n=0; n<frames; ++n) {
        int16_t sample=input[n*channels+slot];
        result.clipped_samples += sample==INT16_MIN || sample==INT16_MAX;
        float window=.5f-.5f*std::cos(2*pi*n/frames);
        window_sum += window;
        workspace.real[n]=(sample/32768.0f)*window;
        workspace.imaginary[n]=0;
    }
    result.window_sum=static_cast<float>(window_sum);
    for (size_t i=1,j=0; i<frames; ++i) {
        size_t bit=frames>>1;
        for (; j & bit; bit>>=1) j^=bit;
        j^=bit;
        if (i<j) {
            std::swap(workspace.real[i],workspace.real[j]);
            std::swap(workspace.imaginary[i],workspace.imaginary[j]);
        }
    }
    for (size_t length=2; length<=frames; length<<=1) {
        float angle=-2*pi/length;
        float step_real=std::cos(angle), step_imaginary=std::sin(angle);
        for (size_t start=0; start<frames; start+=length) {
            float wr=1,wi=0;
            for (size_t offset=0; offset<length/2; ++offset) {
                size_t a=start+offset,b=a+length/2;
                float real=workspace.real[b]*wr-workspace.imaginary[b]*wi;
                float imaginary=workspace.real[b]*wi+workspace.imaginary[b]*wr;
                workspace.real[b]=workspace.real[a]-real;
                workspace.imaginary[b]=workspace.imaginary[a]-imaginary;
                workspace.real[a]+=real;
                workspace.imaginary[a]+=imaginary;
                float next_real=wr*step_real-wi*step_imaginary;
                wi=wr*step_imaginary+wi*step_real;
                wr=next_real;
            }
        }
    }
    int peak=0;
    for (size_t k=0; k<=frames/2; ++k) {
        float factor=(k==0 || k==frames/2) ? 1.0f : 2.0f;
        amplitudes[k]=factor*std::hypot(workspace.real[k],workspace.imaginary[k])/result.window_sum;
        if (amplitudes[k]>amplitudes[peak]) peak=static_cast<int>(k);
    }
    result.peak_amplitude_fs=amplitudes[peak];
    // Float arithmetic needs a declared tolerance when identifying tied peaks.
    float tolerance=std::max(1e-10f,result.peak_amplitude_fs*1e-5f);
    unsigned ties=0;
    for (size_t k=0; k<=frames/2; ++k)
        ties += std::fabs(amplitudes[k]-result.peak_amplitude_fs)<=tolerance;
    if (ties==1 && result.peak_amplitude_fs>=1e-6f) result.peak_bin=peak;
    return true;
}
