#pragma once
#include "lvgl.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "investigation_capture.h"
#include <string>
// All UI creation/enabling with BSP display lock held.
void investigation_ui_init(lv_obj_t* screen,QueueHandle_t media_commands);
void investigation_ui_enable(bool enabled);
void investigation_ui_open();
void investigation_setup_open(); // no-op while a session runs
// Called by the existing media owner for command 4. Returns after a terminal
// state. UI cancel takes effect locally without waiting for this task/network.
void investigation_run(const char* boot);

void investigation_set_endpoint(const char* endpoint);
// USB console tap on start/action/ask/cancel; false when that button is hidden or disabled.
bool investigation_tap(const char* name);
// USB console diagnostic switch: sd_archive or context_photo, 0 or 1.
bool investigation_set(const char* name,bool value);
// USB-only replay of committed SD bytes; never starts sensors.
bool investigation_request_replay(const char* session);
void investigation_run_replay();

// F-0002 T5 (media owner): send a sound-analysis summary (taken) and an optional voice
// note (recorded for this boot/session as <session>-q1) to the Mac; the agent's reading
// comes back as text and is spoken. progress(stage, transcript, text): stage is a short
// status line; text is set once the reading arrives. Called without the display lock.
using SoundExplainProgress=void(*)(const char* stage,const char* transcript,const char* text);
struct SoundExplainResult {std::string transcript,text,error;bool spoke=false;};
bool investigation_explain_sound(const char* boot,const char* session,const InvestigationCapture* note,
                                 cJSON* analysis,SoundExplainProgress progress,SoundExplainResult& out);
// Stops spoken guidance or an explanation being spoken (any task).
void investigation_stop_speech();
