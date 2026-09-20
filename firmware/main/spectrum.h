#pragma once
#include <cstddef>
#include <cstdint>

constexpr size_t spectrum_max_frames = 2048;
struct alignas(16) SpectrumWorkspace {
    float real[spectrum_max_frames];
    float imaginary[spectrum_max_frames];
};
struct SpectrumResult {
    int peak_bin = -1; // No unique peak for silence or tied/flat maxima.
    float peak_amplitude_fs = 0;
    float window_sum = 0;
    size_t clipped_samples = 0;
};

// Periodic Hann, PCM16/32768, one-sided amplitude divided by window sum.
// DC/Nyquist are undoubled. Caller owns separate workspace/output storage.
// No allocation, input mutation, driver calls or physical-channel assumptions.
bool spectrum_pcm16(const int16_t* input, size_t frames, unsigned channels,
                    unsigned slot, SpectrumWorkspace& workspace,
                    float* amplitudes, size_t amplitude_capacity, SpectrumResult& result);
