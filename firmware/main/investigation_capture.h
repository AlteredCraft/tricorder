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
// Only the existing sequential media owner may call this. No speaker playback.
bool investigation_capture(const char* boot,const char* session,const char* id,
                           const std::atomic<bool>& cancel,InvestigationCapture& output);
// Read only a committed SD pair; verify exact extent, identity and digest.
// Never opens codecs or synthesizes acquisition timestamps.
bool investigation_load_capture(const char* base,const char* id,InvestigationCapture& output);
