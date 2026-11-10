#pragma once
// Once after BSP mount and radio preparation, outside the LVGL lock.
// Loads wifi.json and starts the USB console (TRICORDER_CONFIG, TRICORDER_POWER_STEPS).
void test_storage_init(bool mounted,bool connect_saved);
