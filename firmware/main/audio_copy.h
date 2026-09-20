#pragma once
#include <cstddef>
#include <cstdint>

// Playback owns a separate buffer because codec volume processing may write it.
inline bool audio_slot_stereo(const int16_t* raw, size_t frames, unsigned slot,
                              int16_t* output, size_t output_samples) {
    if (!raw || !output || slot >= 4 || frames > output_samples / 2) return false;
    for (size_t frame=0; frame<frames; ++frame)
        output[frame*2] = output[frame*2+1] = raw[frame*4+slot];
    return true;
}
