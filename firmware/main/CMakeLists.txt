idf_component_register(SRCS "diagnostic.cpp" "media.cpp" "network.cpp" "freertos_heap.cpp" "hosted_lifecycle.cpp" "spectrum.cpp" "speech_filter.cpp" "dsp_diagnostic.cpp" "audio_ingress.cpp" "audio_workload.cpp" "audio_devices.cpp" "audio_baseline.cpp" "camera_ingress.cpp" "camera_baseline.cpp" "workload_metrics.cpp" "imu_checked.cpp" "imu_baseline.cpp" "ui_ingress.cpp" "ui_baseline.cpp"
    INCLUDE_DIRS "."
    REQUIRES m5stack_tab5 sensor_bmi270 power_monitor_ina226 json esp_timer
             esp_psram esp_app_format esp_driver_i2c fatfs esp_system spi_flash
             esp_video mbedtls esp_codec_dev esp_wifi esp_netif esp_event
             nvs_flash esp_http_server esp_hosted)
target_link_libraries(${COMPONENT_LIB} INTERFACE "-Wl,--wrap=pvPortMalloc" "-Wl,--wrap=esp_hosted_init" "-Wl,--wrap=i2s_channel_init_tdm_mode" "-Wl,--wrap=i2s_channel_read" "-Wl,--wrap=esp_cam_ctlr_register_event_callbacks" "-Wl,--wrap=esp_video_recv_element" "-Wl,--wrap=bmi270_init" "-Wl,--wrap=esp_lcd_panel_draw_bitmap")
