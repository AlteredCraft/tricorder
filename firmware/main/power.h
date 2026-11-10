#pragma once
#include "lvgl.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
// Power instrument (F-0007): live battery volts, current and watts from the INA226 at
// 10 Hz, then an on-device analysis of the draw. Only meaningful on battery: on USB the
// device runs from USB and the battery branch carries no current. A Screen button steps
// the backlight so the draw of one feature can be seen. Samples stay on the device;
// Explain sends the analysis numbers to the Mac. Sampling runs on the media owner, which
// also does the once-a-second home tile read, so the two never share the I2C bus at once.
constexpr uint8_t power_media_command=14,power_explain_command=15;
// Display lock held. Created hidden.
void power_ui_init(lv_obj_t* screen,QueueHandle_t media_commands);
// Display lock held: shows the screen and asks the media owner to sample.
void power_ui_open();
// Media owner, for power_media_command: samples until the screen closes.
void power_run();
// Media owner, for power_explain_command: asks the Mac to explain the analysis and
// shows and speaks the reply.
void power_explain(const char* boot);
