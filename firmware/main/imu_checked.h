#pragma once
#include "bmi270.h"
// Single sequential owner. Reuse the initialized BSP device; no second I2C handle.
int8_t imu_configure_checked();
// Output is changed only after a successful complete Bosch read.
int8_t imu_read_checked(bmi2_sens_data& output);
void run_imu_baseline(const char* boot_id);
