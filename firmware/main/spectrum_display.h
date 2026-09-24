#pragma once
#include "spectrum.h"

// Display reduction of spectrum_pcm16 output: log-spaced bands in dB relative
// to a full-scale sine. For the on-screen instrument view only; the host
// recomputes every measurement from raw bytes (ADR-0010).
constexpr size_t spectrum_band_count=48;
constexpr float spectrum_band_low_hz=50,spectrum_band_high_hz=20000;
constexpr float spectrum_floor_db=-110,spectrum_ceiling_db=-30;

struct SpectrumBands {
    double power[spectrum_band_count]{};
    unsigned windows=0;
};

// Edge i of band i (lower) and band i-1 (upper); edge 0 is the low limit.
float spectrum_band_edge_hz(size_t edge);
// Accumulates one spectrum_pcm16 amplitude array (fft_frames/2+1 bins). A band
// averages the power of bins whose centre frequency lies inside it; a band
// narrower than one bin uses the bin nearest its geometric centre.
bool spectrum_bands_add(const float* amplitudes,size_t fft_frames,unsigned sample_rate,SpectrumBands& bands);
// Averages consecutive non-overlapping windows of one interleaved slot.
bool spectrum_bands_pcm16(const int16_t* pcm,size_t frames,unsigned channels,unsigned slot,
                          size_t window_frames,unsigned sample_rate,SpectrumWorkspace& workspace,
                          float* amplitudes,size_t amplitude_capacity,SpectrumBands& bands);
// Mean power per band in dB, never below spectrum_floor_db (silence included).
void spectrum_bands_db(const SpectrumBands& bands,float* db);
// Linear 0..100 chart value across [floor, ceiling], clamped.
int32_t spectrum_chart_value(float db);
