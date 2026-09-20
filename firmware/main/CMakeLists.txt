idf_component_register(SRCS "diagnostic.cpp"
    INCLUDE_DIRS "."
    REQUIRES m5stack_tab5 sensor_bmi270 power_monitor_ina226 json esp_timer
             esp_psram esp_app_format esp_driver_i2c fatfs esp_system spi_flash)
