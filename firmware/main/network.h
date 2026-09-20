#pragma once
#include "lvgl.h"

// Called with the LVGL lock held; network work runs outside the UI task.
void network_ui_init(lv_obj_t* screen, const char* boot_id);
