#pragma once
#include "cJSON.h"

cJSON* diagnostic_event(const char* name);
void diagnostic_emit(cJSON* event);
void diagnostic_check(const char* name, const char* result, const char* detail);
void diagnostic_stage(const char* text);
