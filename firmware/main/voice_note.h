#pragma once
#include <atomic>
#include <cstddef>
#include "cJSON.h"
// A spoken note for the Mac to transcribe (ADR-0006/0013): 16 kHz mono speech and the
// metadata the service checks (planning/service.md, question metadata).
struct VoiceNote {
    unsigned char* bytes=nullptr;
    size_t size=0;
    cJSON* metadata=nullptr;
    ~VoiceNote();
    VoiceNote()=default;
    VoiceNote(const VoiceNote&)=delete;
    VoiceNote& operator=(const VoiceNote&)=delete;
};
// Only the media owner may call this. No speaker playback. Microphone slot 0 is filtered
// to 16 kHz mono (SpeechFilter) while recording; stops when `stop` is set after at least
// one block, at 8 s, or fails on cancel/driver loss. `level` receives each block's
// filtered RMS in dBFS for a live level meter.
using VoiceLevelTap=void(*)(float dbfs);
bool voice_note_record(const char* boot,const char* session,const char* id,
                       const std::atomic<bool>& cancel,const std::atomic<bool>& stop,
                       VoiceNote& output,VoiceLevelTap level=nullptr);
