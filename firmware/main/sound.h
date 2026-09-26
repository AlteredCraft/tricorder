#pragma once
#include "lvgl.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
// Sound instrument (F-0001 T2, F-0002): live spectrum, peak hold and level from slot 0,
// then an on-device analysis. The listening audio is never saved or sent; Explain sends
// the analysis numbers and an optional voice note to the Mac.
constexpr uint8_t sound_media_command=7,sound_note_command=8,sound_explain_command=9;
// Display lock held. Created hidden.
void sound_ui_init(lv_obj_t* screen,QueueHandle_t media_commands);
// Display lock held: shows the screen and asks the media owner to listen.
void sound_ui_open();
// Media owner, for sound_media_command: listens until the screen closes.
void sound_run();
// Media owner, F-0002 T5: record the voice note (until Stop or 8 s), and ask the Mac
// to explain the analysis with it.
void sound_record_note(const char* boot);
void sound_explain(const char* boot);
