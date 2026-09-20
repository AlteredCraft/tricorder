#pragma once
#include <cstdint>

struct AudioIngressSnapshot {
    uint64_t dma_bytes=0,dma_buffers=0,overwritten_bytes=0,overflows=0;
    uint64_t read_bytes=0,read_calls=0,short_reads=0,read_errors=0;
};
AudioIngressSnapshot audio_ingress_snapshot();
// Called only by the synchronous capture owner after opening/configuring codec.
// Clears stale RX queues using the IDF lifecycle; preserves lifetime counters.
bool begin_audio_epoch(AudioIngressSnapshot& before);
