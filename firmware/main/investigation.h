#pragma once
#include "lvgl.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
// All UI creation/enabling with BSP display lock held.
void investigation_ui_init(lv_obj_t* screen,QueueHandle_t media_commands);
void investigation_ui_enable(bool enabled);
void investigation_ui_open();
// Called by the existing media owner for command 4. Returns after a terminal
// state. UI cancel takes effect locally without waiting for this task/network.
void investigation_run(const char* boot);

void investigation_set_endpoint(const char* endpoint);
// USB-only replay of committed SD bytes; never starts sensors.
bool investigation_request_replay(const char* session);
void investigation_run_replay();
