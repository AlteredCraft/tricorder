#pragma once
#include <atomic>
#include <cstddef>
#include "cJSON.h"
struct InvestigationCapture {
    unsigned char* bytes=nullptr;
    size_t size=0;
    cJSON* metadata=nullptr;
    cJSON* measurement=nullptr;
    ~InvestigationCapture();
    InvestigationCapture()=default;
    InvestigationCapture(const InvestigationCapture&)=delete;
    InvestigationCapture& operator=(const InvestigationCapture&)=delete;
};
// Display-only live view: dB bands (spectrum_display.h) of the latest 2048
// measurement-slot frames, called from the capture loop about every 85 ms.
// Must not block; the I2S DMA ring holds only ~30 ms.
using CaptureSpectrumTap=void(*)(const float* db);
// Only the existing sequential media owner may call this. No speaker playback.
bool investigation_capture(const char* boot,const char* session,const char* id,
                           const std::atomic<bool>& cancel,InvestigationCapture& output,
                           CaptureSpectrumTap tap=nullptr);
// Read only a committed SD pair; verify exact extent, identity and digest.
// Never opens codecs or synthesizes acquisition timestamps.
bool investigation_load_capture(const char* base,const char* id,InvestigationCapture& output);
