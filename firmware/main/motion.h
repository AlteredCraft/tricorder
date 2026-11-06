#pragma once
#include "lvgl.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
// Motion instrument (F-0005): live acceleration and tilt traces from the BMI270 at 100 Hz,
// then an on-device analysis. Samples stay on the device; Explain sends the analysis
// numbers to the Mac. Sampling runs on the media owner, which also does the once-a-second
// home tile read, so the two never share the I2C bus at once.
constexpr uint8_t motion_media_command=10,motion_explain_command=11;
// Display lock held. Created hidden.
void motion_ui_init(lv_obj_t* screen,QueueHandle_t media_commands);
// Display lock held: shows the screen and asks the media owner to sample.
void motion_ui_open();
// Media owner, for motion_media_command: samples until the screen closes.
void motion_run();
// Media owner, for motion_explain_command: asks the Mac to explain the analysis and
// shows and speaks the reply.
void motion_explain(const char* boot);
