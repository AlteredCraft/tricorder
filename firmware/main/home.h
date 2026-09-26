#pragma once
#include "lvgl.h"
// Start screen (F-0001): one tile per capability. All calls except home_readings
// need the display lock. Created hidden, after the other panels.
void home_ui_init(lv_obj_t* screen);
void home_ui_open();
// Media owner, about once a second: the readings the tiles show.
void home_readings(float tilt_degrees,float bus_v,float shunt_a,bool headphones);
// A panel closed; logs ui_nav. to=nullptr means whichever of home/diagnostics is showing.
void home_returned(const char* from,const char* to=nullptr);
