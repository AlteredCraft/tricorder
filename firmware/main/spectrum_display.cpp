#include "spectrum_display.h"
#include <algorithm>
#include <cmath>

float spectrum_band_edge_hz(size_t edge) {
    return spectrum_band_low_hz*std::pow(spectrum_band_high_hz/spectrum_band_low_hz,
                                         static_cast<float>(edge)/spectrum_band_count);
}

bool spectrum_bands_add(const float* amplitudes,size_t fft_frames,unsigned sample_rate,SpectrumBands& bands) {
    if(!amplitudes || fft_frames<8 || !sample_rate)return false;
    const double bin_hz=static_cast<double>(sample_rate)/fft_frames;
    const size_t bins=fft_frames/2+1;
    for(size_t band=0;band<spectrum_band_count;++band) {
        const double low=spectrum_band_edge_hz(band),high=spectrum_band_edge_hz(band+1);
        size_t first=static_cast<size_t>(std::ceil(low/bin_hz)),count=0;
        double sum=0;
        for(size_t k=first;k<bins && k*bin_hz<high;++k){sum+=double(amplitudes[k])*amplitudes[k];++count;}
        if(!count) {
            const size_t k=std::min(bins-1,static_cast<size_t>(std::lround(std::sqrt(low*high)/bin_hz)));
            sum=double(amplitudes[k])*amplitudes[k];count=1;
        }
        bands.power[band]+=sum/count;
    }
    ++bands.windows;
    return true;
}

bool spectrum_bands_pcm16(const int16_t* pcm,size_t frames,unsigned channels,unsigned slot,
                          size_t window_frames,unsigned sample_rate,SpectrumWorkspace& workspace,
                          float* amplitudes,size_t amplitude_capacity,SpectrumBands& bands) {
    if(!pcm || !channels || window_frames<8 || frames<window_frames)return false;
    bands={};
    SpectrumResult result;
    for(size_t start=0;start+window_frames<=frames;start+=window_frames)
        if(!spectrum_pcm16(pcm+start*channels,window_frames,channels,slot,workspace,
                           amplitudes,amplitude_capacity,result) ||
           !spectrum_bands_add(amplitudes,window_frames,sample_rate,bands))return false;
    return true;
}

void spectrum_bands_db(const SpectrumBands& bands,float* db) {
    for(size_t band=0;band<spectrum_band_count;++band) {
        const double power=bands.windows?bands.power[band]/bands.windows:0;
        db[band]=power>0?std::max(spectrum_floor_db,static_cast<float>(10*std::log10(power))):spectrum_floor_db;
    }
}

int32_t spectrum_chart_value(float db) {
    const float scaled=100*(db-spectrum_floor_db)/(spectrum_ceiling_db-spectrum_floor_db);
    return static_cast<int32_t>(std::lround(std::clamp(scaled,0.0f,100.0f)));
}
