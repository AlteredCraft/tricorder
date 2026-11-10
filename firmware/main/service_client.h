#pragma once
#include "cJSON.h"
#include "voice_note.h"
#include <cstddef>
#include <string>

// Explain (media owner): send an instrument's analysis summary (taken; its "kind" is sound,
// motion, camera or power) to the Mac service; the agent's reading comes back as text and
// is spoken. An optional voice note (recorded for this boot/session) is transcribed first.
// Hooks run on the media task without the display lock:
// progress(stage, transcript, text) gives a short status line, then the reading's text.
// With show_transcript, the note's transcript (status heard, empty or failed) is shown
// and poll_choice is polled until it returns 1 explain, 2 record again or 0 cancel;
// without it, a heard note is used as is.
struct AnalysisExplainHooks {
    void(*progress)(const char* stage,const char* transcript,const char* text);
    void(*show_transcript)(const char* status,const char* text)=nullptr;
    int(*poll_choice)()=nullptr;
};
struct AnalysisExplainResult {std::string transcript,text,error;bool spoke=false;int choice=1;};
// Camera: a photo (JPEG bytes) goes up in photo_chunk messages before the analysis that
// describes it.
bool service_explain_analysis(const char* boot,const char* session,const VoiceNote* note,
                              cJSON* analysis,const AnalysisExplainHooks& hooks,AnalysisExplainResult& out,
                              const unsigned char* photo=nullptr,size_t photo_bytes=0);
// Stops an explanation being spoken (any task).
void service_stop_speech();
