#pragma once
#include "lvgl.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
// Camera instrument (F-0006): a live half-size view from the CSI camera, a photo kept at
// full size as a JPEG, and Explain, which sends the photo to the Mac's local vision model
// with a fixed question. The live view is never sent. Streaming and encoding run on the
// media owner; the LVGL timer only swaps the view between two owned buffers.
constexpr uint8_t camera_media_command=12,camera_explain_command=13;
// Display lock held. Created hidden.
void camera_ui_init(lv_obj_t* screen,QueueHandle_t media_commands);
// Display lock held: shows the screen and asks the media owner to stream.
void camera_ui_open();
// Media owner, for camera_media_command: streams until the screen closes or a photo is
// taken, then encodes the photo.
void camera_run();
// Media owner, for camera_explain_command: sends the photo to the Mac and shows and
// speaks the reply.
void camera_explain(const char* boot);
