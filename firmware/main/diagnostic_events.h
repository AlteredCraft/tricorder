#pragma once
#include "cJSON.h"

cJSON* diagnostic_event(const char* name);
void diagnostic_emit(cJSON* event);
void diagnostic_check(const char* name, const char* result, const char* detail);
void diagnostic_stage(const char* text);
// USB console: queue the INA226 power-step test on the media owner (G-0001.05 C1).
bool diagnostic_request_power_steps();
// Media owner only (F-0007): one INA226 reading of the battery branch, volts and amps out
// of the battery; false when the monitor is not ready.
bool diagnostic_power_read(float& bus_v,float& shunt_a);
