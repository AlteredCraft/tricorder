#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <unistd.h>
#include <inttypes.h>
#include "bsp/m5stack_tab5.h"
#include "diagnostic_events.h"
#include "media.h"
#include "network.h"
#include "audio_devices.h"
#include "restart_sequence.h"
#include "dsp_diagnostic.h"
#include "esp_attr.h"
#include <atomic>
#include "accel_gyro_bmi270.h"
#include "ina226.hpp"
#include "cJSON.h"
#include "esp_app_desc.h"
#include "esp_chip_info.h"
#include "esp_flash.h"
#include "esp_heap_caps.h"
#include "esp_psram.h"
#include "esp_random.h"
#include "esp_rom_crc.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/queue.h"
#include "freertos/task.h"

// The factory BSP owns I2C, IO expanders, display and touch. Each remaining
// driver shares its I2C handle; no second bus initialization is permitted.
static char boot_id[33];
static uint32_t sequence;
static SemaphoreHandle_t event_mutex;
static INA226 power_monitor;
static bool imu_ready;
static bool power_ready;
static lv_obj_t* status_label;
static lv_obj_t* record_button;
static lv_obj_t* volume_label;
static lv_obj_t* restart_button;
static lv_obj_t* baseline_button;
static QueueHandle_t media_commands;
static std::atomic<bool> initialization_failed{false};
RTC_NOINIT_ATTR static RestartSequence restart_sequence;

void diagnostic_stage(const char* text) {
    if (status_label && bsp_display_lock(1000)) {
        lv_label_set_text(status_label, text);
        lv_obj_center(status_label);
        bsp_display_unlock();
    }
    auto* event=diagnostic_event("display_stage");
    cJSON_AddStringToObject(event,"text",text);
    diagnostic_emit(event);
}

cJSON* diagnostic_event(const char* name) {
    auto* e = cJSON_CreateObject();
    configASSERT(e);
    cJSON_AddStringToObject(e, "event", name);
    return e;
}

void diagnostic_emit(cJSON* e) {
    xSemaphoreTake(event_mutex, portMAX_DELAY);
    cJSON_AddStringToObject(e, "boot_id", boot_id);
    cJSON_AddNumberToObject(e, "seq", sequence++);
    cJSON_AddNumberToObject(e, "device_us", esp_timer_get_time());
    char* line = cJSON_PrintUnformatted(e);
    configASSERT(line);
    printf("TRICORDER %s\n", line);
    fflush(stdout);
    cJSON_free(line);
    cJSON_Delete(e);
    xSemaphoreGive(event_mutex);
}

void diagnostic_check(const char* name, const char* result, const char* detail) {
    if (strcmp(result, "fail") == 0) initialization_failed.store(true);
    auto* e = diagnostic_event("check");
    cJSON_AddStringToObject(e, "check", name);
    cJSON_AddStringToObject(e, "result", result);
    cJSON_AddStringToObject(e, "detail", detail);
    diagnostic_emit(e);
}

static esp_err_t read_register(uint8_t address, uint16_t reg, size_t reg_size,
                               uint8_t* data, size_t size) {
    i2c_device_config_t config{};
    config.dev_addr_length = I2C_ADDR_BIT_LEN_7;
    config.device_address = address;
    config.scl_speed_hz = 100000;
    i2c_master_dev_handle_t handle = nullptr;
    auto result = i2c_master_bus_add_device(bsp_i2c_get_handle(), &config, &handle);
    if (result != ESP_OK) return result;
    uint8_t registers[] = {static_cast<uint8_t>(reg >> 8), static_cast<uint8_t>(reg)};
    result = i2c_master_transmit_receive(handle, registers + (2-reg_size), reg_size,
                                         data, size, 100);
    i2c_master_bus_rm_device(handle);
    return result;
}

static void identity(const char* name, uint8_t addr, uint16_t reg, size_t reg_size,
                     size_t bytes, int expected) {
    uint8_t data[2]{};
    auto result = read_register(addr, reg, reg_size, data, bytes);
    int value = bytes == 2 ? (data[0] << 8) | data[1] : data[0];
    auto* e = diagnostic_event("identity");
    cJSON_AddStringToObject(e, "component", name);
    cJSON_AddNumberToObject(e, "address", addr);
    cJSON_AddNumberToObject(e, "register", reg);
    cJSON_AddNumberToObject(e, "value", value);
    cJSON_AddStringToObject(e, "read_result", esp_err_to_name(result));
    diagnostic_emit(e);
    diagnostic_check(name, result == ESP_OK && value == expected ? "pass" : "fail",
          "Register identity only; does not establish functional capability.");
}

static int rtc_second() {
    uint8_t value{};
    if (read_register(0x32, 0x10, 1, &value, 1) != ESP_OK) return -1;
    value &= 0x7f;
    if ((value & 15) > 9 || (value >> 4) > 5) return -1;
    return (value >> 4)*10 + (value & 15);
}

static void sd_roundtrip() {
    char mount[] = "/sdcard";
    auto result = bsp_sdcard_init(mount, 3); // Vendor mount never formats on failure.
    if (result != ESP_OK) {
        diagnostic_check("sd_roundtrip", "inconclusive", esp_err_to_name(result));
        return;
    }
    char path[96];
    snprintf(path, sizeof(path), "/sdcard/tri-%s.bin", boot_id);
    uint8_t written[1024], readback[1024];
    for (size_t i=0; i<sizeof(written); ++i) written[i] = (i*37+11) & 255;
    int fd = open(path, O_WRONLY | O_CREAT | O_EXCL, 0600);
    bool ok = fd >= 0;
    if (fd >= 0) {
        ok = write(fd, written, sizeof(written)) == sizeof(written);
        ok = fsync(fd) == 0 && ok;
        ok = close(fd) == 0 && ok;
    }
    fd = open(path, O_RDONLY);
    if (fd >= 0) {
        ok = read(fd, readback, sizeof(readback)) == sizeof(readback) && ok;
        close(fd);
        ok = ok && memcmp(written, readback, sizeof(written)) == 0;
    } else ok = false;
    auto* e = diagnostic_event("sd_readback");
    cJSON_AddStringToObject(e, "path", path);
    cJSON_AddNumberToObject(e, "size_bytes", sizeof(written));
    cJSON_AddNumberToObject(e, "expected_crc32", esp_rom_crc32_le(0, written, sizeof(written)));
    if (ok) cJSON_AddNumberToObject(e, "read_crc32", esp_rom_crc32_le(0, readback, sizeof(readback)));
    diagnostic_emit(e);
    diagnostic_check("sd_roundtrip", ok ? "pass" : "fail", "Exclusive new file; fsync, reopen, byte comparison and CRC32.");
}

static void touch_event(lv_event_t* ev) {
    auto* indev = lv_event_get_indev(ev);
    if (!indev) return;
    lv_point_t point{};
    lv_indev_get_point(indev, &point);
    auto* e = diagnostic_event("touch");
    cJSON_AddNumberToObject(e, "x", point.x);
    cJSON_AddNumberToObject(e, "y", point.y);
    diagnostic_emit(e);
}

static void record_clicked(lv_event_t*) {
    uint8_t command = 1;
    // UI never waits for capture/export/playback. Ignore repeats while busy.
    bool accepted=xQueueSend(media_commands, &command, 0)==pdTRUE;
    if (accepted) {
        lv_obj_add_state(record_button, LV_STATE_DISABLED);
        lv_obj_add_state(restart_button, LV_STATE_DISABLED);
        lv_obj_add_state(baseline_button, LV_STATE_DISABLED);
    }
    auto* event=diagnostic_event("audio_button");
    cJSON_AddBoolToObject(event,"accepted",accepted);
    diagnostic_emit(event);
}

static void restart_clicked(lv_event_t*) {
    uint8_t command=2;
    if (xQueueSend(media_commands, &command, 0)==pdTRUE) {
        lv_obj_add_state(restart_button, LV_STATE_DISABLED);
        lv_obj_add_state(record_button, LV_STATE_DISABLED);
        lv_obj_add_state(baseline_button, LV_STATE_DISABLED);
    }
}

static void baseline_clicked(lv_event_t*) {
    uint8_t command=3;
    if (xQueueSend(media_commands,&command,0)==pdTRUE) {
        lv_obj_add_state(record_button,LV_STATE_DISABLED);
        lv_obj_add_state(restart_button,LV_STATE_DISABLED);
        lv_obj_add_state(baseline_button,LV_STATE_DISABLED);
    }
}

static void continue_restarts() {
    const auto series=restart_sequence.series();
    const auto completed=restart_sequence.completed();
    if (initialization_failed.load() || completed==10) {
        auto* event=diagnostic_event(initialization_failed.load() ? "software_reset_aborted" : "software_reset_complete");
        cJSON_AddNumberToObject(event, "series_id", series);
        cJSON_AddNumberToObject(event, "cycle", completed);
        diagnostic_emit(event);
        restart_sequence.clear();
        return;
    }
    unsigned cycle=restart_sequence.next();
    if (!cycle) return;
    char text[160];
    snprintf(text,sizeof(text),"SOFTWARE RESTART TEST\n\nRestart %u of 10\nInitialization checks repeat after every restart.",cycle);
    diagnostic_stage(text);
    auto* event=diagnostic_event("software_reset_requested");
    cJSON_AddNumberToObject(event, "series_id", series);
    cJSON_AddNumberToObject(event, "cycle", cycle);
    diagnostic_emit(event);
    vTaskDelay(pdMS_TO_TICKS(2000));
    esp_restart();
}

static void volume_changed(lv_event_t* event) {
    auto* slider = static_cast<lv_obj_t*>(lv_event_get_target(event));
    unsigned volume = lv_slider_get_value(slider);
    set_playback_volume(volume);
    lv_label_set_text_fmt(volume_label, "Playback volume: %u%%", volume);
    auto* record = diagnostic_event("playback_volume_changed");
    cJSON_AddNumberToObject(record, "volume_percent", volume);
    diagnostic_emit(record);
}

static void media_idle() {
    diagnostic_stage("TRICORDER / hardware diagnostic\n\nTap Record & play when ready.\nWait for RECORDING, then say the test phrase.\nListen to slots 0, 1, 2 and 3.\n\nStorage checks await a microSD card.");
    if (bsp_display_lock(1000)) {
        lv_obj_remove_state(record_button, LV_STATE_DISABLED);
        lv_obj_remove_state(restart_button, LV_STATE_DISABLED);
        lv_obj_remove_state(baseline_button, LV_STATE_DISABLED);
        bsp_display_unlock();
    }
    diagnostic_emit(diagnostic_event("audio_test_ready"));
}

extern "C" void app_main() {
    event_mutex = xSemaphoreCreateMutex();
    configASSERT(event_mutex);
    media_commands = xQueueCreate(1, sizeof(uint8_t));
    configASSERT(media_commands);
    uint32_t random[4];
    esp_fill_random(random, sizeof(random));
    snprintf(boot_id, sizeof(boot_id), "%08" PRIx32 "%08" PRIx32 "%08" PRIx32 "%08" PRIx32,
             random[0], random[1], random[2], random[3]);
    esp_chip_info_t chip{};
    esp_chip_info(&chip);
    uint32_t flash_bytes{};
    ESP_ERROR_CHECK(esp_flash_get_size(nullptr, &flash_bytes));
    auto* boot = diagnostic_event("boot");
    cJSON_AddStringToObject(boot, "firmware", esp_app_get_description()->version);
    cJSON_AddStringToObject(boot, "idf", esp_get_idf_version());
    cJSON_AddNumberToObject(boot, "chip_revision", chip.revision);
    cJSON_AddNumberToObject(boot, "flash_bytes", flash_bytes);
    cJSON_AddNumberToObject(boot, "psram_bytes", esp_psram_get_size());
    cJSON_AddNumberToObject(boot, "reset_reason", esp_reset_reason());
    diagnostic_emit(boot);
    bool resuming_restarts=restart_sequence.resume(esp_reset_reason()==ESP_RST_SW);
    if (resuming_restarts) {
        auto* event=diagnostic_event("software_reset_resumed");
        cJSON_AddNumberToObject(event,"series_id",restart_sequence.series());
        cJSON_AddNumberToObject(event,"cycle",restart_sequence.completed());
        diagnostic_emit(event);
    }

    ESP_ERROR_CHECK(bsp_cam_osc_init());
    ESP_ERROR_CHECK(bsp_i2c_init());
    bsp_io_expander_pi4ioe_init(bsp_i2c_get_handle());
    bsp_set_charge_qc_en(true);
    vTaskDelay(pdMS_TO_TICKS(50));
    bsp_set_charge_en(true);
    identity("imu_id", 0x68, 0x00, 1, 1, 0x24);
    identity("ina226_manufacturer", 0x41, 0xfe, 1, 2, 0x5449);
    // The pinned factory enables SC202CS (PID 0xeb52); retain the actual read
    // independently of the product page's SC2356 name.
    identity("camera_driver_id", 0x36, 0x3107, 2, 2, 0xeb52);
    imu_ready = accel_gyro_bmi270_init(bsp_i2c_get_handle()) == ESP_OK;
    if (imu_ready) accel_gyro_bmi270_enable_sensor();
    diagnostic_check("imu_initialize", imu_ready ? "pass" : "fail", "BMI270 driver initialization; no calibration claim.");
    power_ready = power_monitor.begin(bsp_i2c_get_handle(), 0x41)
        && power_monitor.configure(INA226_AVERAGES_16, INA226_BUS_CONV_TIME_1100US,
                                  INA226_SHUNT_CONV_TIME_1100US, INA226_MODE_SHUNT_BUS_CONT)
        && power_monitor.calibrate(0.005, 8.192);
    diagnostic_check("power_initialize", power_ready ? "pass" : "fail", "INA226 driver setup only; physical rail/sign accuracy unverified.");

    bsp_reset_tp();
    // Factory-verified full-frame PSRAM buffers. The BSP convenience default
    // uses a small internal allocation whose rotation buffer fails PPA alignment.
    bsp_display_cfg_t display_config{};
    display_config.lvgl_port_cfg = ESP_LVGL_PORT_INIT_CONFIG();
    display_config.buffer_size = BSP_LCD_H_RES * BSP_LCD_V_RES;
    display_config.double_buffer = true;
    display_config.flags.buff_dma = true;
    display_config.flags.buff_spiram = true;
    display_config.flags.sw_rotate = true;
    auto* display = bsp_display_start_with_config(&display_config);
    configASSERT(display);
    // The BSP has already started the LVGL task and returns with no lock held.
    // Protect the entire object-construction phase from concurrent refresh.
    configASSERT(bsp_display_lock(0));
    lv_display_set_rotation(display, LV_DISPLAY_ROTATION_90);
    auto* screen = lv_screen_active();
    lv_obj_add_event_cb(screen, touch_event, LV_EVENT_PRESSED, nullptr);
    auto* label = lv_label_create(screen);
    status_label = label;
    lv_obj_set_style_text_font(label, &lv_font_montserrat_32, 0);
    lv_obj_set_style_text_align(label, LV_TEXT_ALIGN_CENTER, 0);
    lv_label_set_text(label, "TRICORDER / hardware diagnostic\n\nTouch all four corners and the center.\nTilt the device to record motion.\n\nCamera/audio/network checks pending.");
    lv_obj_center(label);
    lv_obj_add_flag(label, LV_OBJ_FLAG_EVENT_BUBBLE);
    record_button = lv_button_create(screen);
    lv_obj_set_size(record_button, 240, 70);
    lv_obj_align(record_button, LV_ALIGN_BOTTOM_MID, 0, -30);
    lv_obj_add_state(record_button, LV_STATE_DISABLED);
    lv_obj_add_event_cb(record_button, record_clicked, LV_EVENT_CLICKED, nullptr);
    auto* button_label = lv_label_create(record_button);
    lv_label_set_text(button_label, "Record & play");
    lv_obj_center(button_label);
    auto* volume_slider = lv_slider_create(screen);
    lv_obj_set_pos(volume_slider, 920, 658);
    lv_obj_set_size(volume_slider, 290, 18);
    lv_slider_set_range(volume_slider, 0, 100);
    lv_slider_set_value(volume_slider, 80, LV_ANIM_OFF);
    volume_label = lv_label_create(screen);
    lv_obj_set_pos(volume_label, 920, 614);
    lv_label_set_text(volume_label, "Playback volume: 80%");
    lv_obj_add_event_cb(volume_slider, volume_changed, LV_EVENT_VALUE_CHANGED, nullptr);
    restart_button=lv_button_create(screen);
    lv_obj_set_pos(restart_button,30,70);
    lv_obj_set_size(restart_button,230,58);
    lv_obj_add_state(restart_button,LV_STATE_DISABLED);
    lv_obj_add_event_cb(restart_button,restart_clicked,LV_EVENT_CLICKED,nullptr);
    auto* restart_label=lv_label_create(restart_button);
    lv_label_set_text(restart_label,"Test 10 restarts");
    lv_obj_center(restart_label);
    baseline_button=lv_button_create(screen);
    lv_obj_set_pos(baseline_button,30,145);
    lv_obj_set_size(baseline_button,230,58);
    lv_obj_add_state(baseline_button,LV_STATE_DISABLED);
    lv_obj_add_event_cb(baseline_button,baseline_clicked,LV_EVENT_CLICKED,nullptr);
    auto* baseline_label=lv_label_create(baseline_button);
    lv_label_set_text(baseline_label,"Audio baseline 60s");
    lv_obj_center(baseline_label);
    network_ui_init(screen, boot_id);
    bsp_display_brightness_set(50);
    bsp_display_unlock();
    auto* panel = diagnostic_event("display_initialized");
    cJSON_AddStringToObject(panel, "driver", bsp_display_get_panel_ic());
    diagnostic_emit(panel);
    diagnostic_check("display_initialize", "pass", "Display/LVGL initialized; physical touch fixture remains separate.");

    int start_second = rtc_second();
    vTaskDelay(pdMS_TO_TICKS(1100));
    int end_second = rtc_second();
    int elapsed = (end_second-start_second+60)%60;
    diagnostic_check("rtc_advance", start_second >= 0 && end_second >= 0 && elapsed >= 1 && elapsed <= 2
        ? "pass" : "fail", "Seconds register advances; calendar accuracy is not established.");
    sd_roundtrip();
    diagnostic_emit(diagnostic_event("ready"));
    capture_camera(boot_id);
    // Three isolated live raw/speech comparisons, without operator input.
    for (unsigned repetition=0;repetition<3;++repetition) capture_audio(boot_id);
    diagnostic_stage("Checking radio initialization...");
    diagnostic_check("wifi_initialize",network_prepare(30000) ? "pass" : "fail",
                     "Hosted radio initialization and C6 version query; no network association claim.");
    run_dsp_fixtures(boot_id);
    run_speech_fixtures(boot_id);
    // Autonomous isolated baseline while the operator is away.
    if (!resuming_restarts && !initialization_failed.load()) run_audio_baseline(boot_id);
    if (resuming_restarts) continue_restarts();
    media_idle();
    for (;;) {
        uint8_t command;
        if (xQueueReceive(media_commands, &command, 0) == pdTRUE) {
            if (command==2) {
                restart_sequence.start(esp_random());
                continue_restarts();
            } else if (command==3) run_audio_baseline(boot_id);
            else capture_audio(boot_id, true);
            media_idle();
        }
        auto* e = diagnostic_event("telemetry");
        cJSON_AddNumberToObject(e, "free_internal", heap_caps_get_free_size(MALLOC_CAP_INTERNAL));
        cJSON_AddNumberToObject(e, "free_psram", heap_caps_get_free_size(MALLOC_CAP_SPIRAM));
        if (imu_ready) {
            bmi2_sens_data data{};
            accel_gyro_bmi270_get_data(&data);
            cJSON_AddNumberToObject(e, "accel_x_raw", data.acc.x);
            cJSON_AddNumberToObject(e, "accel_y_raw", data.acc.y);
            cJSON_AddNumberToObject(e, "accel_z_raw", data.acc.z);
        }
        if (power_ready) {
            cJSON_AddNumberToObject(e, "ina226_bus_v", power_monitor.readBusVoltage());
            cJSON_AddNumberToObject(e, "ina226_shunt_a", power_monitor.readShuntCurrent());
        }
        diagnostic_emit(e);
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}
