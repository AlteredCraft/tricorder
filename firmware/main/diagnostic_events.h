#pragma once
#include "cJSON.h"

cJSON* diagnostic_event(const char* name);
void diagnostic_emit(cJSON* event);
void diagnostic_check(const char* name, const char* result, const char* detail);
void diagnostic_stage(const char* text);
// USB console: queue the INA226 power-step test on the media owner (G-0001.05 C1).
bool diagnostic_request_power_steps();
