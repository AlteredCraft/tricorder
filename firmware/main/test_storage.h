#pragma once
#include "cJSON.h"
#include "esp_http_server.h"
#include <cstddef>
// Once after BSP mount and radio preparation, outside the LVGL lock.
void test_storage_init(const char* boot,bool mounted,bool connect_saved);
bool test_storage_archive(const unsigned char* bytes,size_t size,const cJSON* metadata);
struct InvestigationCapture;
bool test_storage_load_capture(const char* id,InvestigationCapture& output);
void test_storage_http(httpd_handle_t server);
