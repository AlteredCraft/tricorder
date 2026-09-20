#include "imu_checked.h"
#include "diagnostic_events.h"
#include "workload_metrics.h"
#include "media.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <cstdio>
#include <cstdlib>

struct ImuMemory {size_t internal,external,largest,stack,sram,largest_sram;};

void run_imu_baseline(const char* boot_id) {
    constexpr size_t samples=6000,columns=13;
    auto* rows=static_cast<int32_t*>(heap_caps_malloc(samples*columns*sizeof(int32_t),MALLOC_CAP_SPIRAM));
    auto* memory=static_cast<ImuMemory*>(calloc(60,sizeof(ImuMemory)));
    if (!rows || !memory) {
        free(rows);free(memory);diagnostic_check("imu_baseline","fail","IMU evidence allocation failed.");return;
    }
    diagnostic_stage("MOTION BASELINE / 60 seconds\n\nAutomatic accelerometer and gyroscope checks.\nNo movement or interaction is needed.");
    // Configuration was checked at startup. Clear the prior data-ready state;
    // sample latest registers at 100 Hz while hardware produces at 200 Hz.
    vTaskDelay(pdMS_TO_TICKS(20));
    bmi2_sens_data warmup{};
    const auto warmup_result=imu_read_checked(warmup);
    auto* cpu_before=workload_cpu_snapshot();
    TickType_t wake=xTaskGetTickCount();
    const int64_t started=esp_timer_get_time();
    size_t count=0,read_errors=0,not_ready=0,repeated=0,missed=0;
    uint32_t previous_sensor_time=0;bool have_previous=false;
    for (;count<samples;++count) {
        vTaskDelayUntil(&wake,pdMS_TO_TICKS(10));
        const int64_t read_start=esp_timer_get_time();
        bmi2_sens_data data{};const auto result=imu_read_checked(data);
        const int64_t read_end=esp_timer_get_time();
        auto* r=rows+count*columns;
        r[0]=count+1;r[1]=(count+1)*10000;r[2]=read_start-started;r[3]=read_end-started;
        r[4]=result;r[5]=data.sens_time;r[6]=data.status;
        r[7]=data.acc.x;r[8]=data.acc.y;r[9]=data.acc.z;
        r[10]=data.gyr.x;r[11]=data.gyr.y;r[12]=data.gyr.z;
        if (result!=BMI2_OK) ++read_errors;
        else {
            if ((data.status&(BMI2_DRDY_ACC|BMI2_DRDY_GYR))!=(BMI2_DRDY_ACC|BMI2_DRDY_GYR)) ++not_ready;
            if (have_previous && previous_sensor_time==data.sens_time) ++repeated;
            previous_sensor_time=data.sens_time;have_previous=true;
        }
        if (r[3]>r[1]+10000) ++missed;
        if ((count+1)%100==0) {
            auto& m=memory[count/100];
            m.internal=heap_caps_get_free_size(MALLOC_CAP_INTERNAL);m.external=heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
            m.largest=heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM);m.stack=uxTaskGetStackHighWaterMark(nullptr);
            constexpr auto caps=MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT|MALLOC_CAP_SIMD;
            m.sram=heap_caps_get_free_size(caps);m.largest_sram=heap_caps_get_largest_free_block(caps);
        }
        if (read_end-started>65000000) {++count;break;}
    }
    const int64_t ended=esp_timer_get_time();auto* cpu_after=workload_cpu_snapshot();
    auto* meta=diagnostic_event("capture_start");
    cJSON_AddStringToObject(meta,"format","imu_baseline_i32le");
    cJSON_AddStringToObject(meta,"layout","sequence,scheduled_us,read_start_us,read_end_us,result,sensor_time,status,accel_xyz,gyro_xyz; device times relative to epoch; sensor_time is raw 24-bit register counter");
    cJSON_AddStringToObject(meta,"policy","latest-register-sample; intermediate hardware samples intentionally not retained");
    cJSON_AddNumberToObject(meta,"rows",count);cJSON_AddNumberToObject(meta,"columns",columns);
    cJSON_AddNumberToObject(meta,"period_us",10000);cJSON_AddNumberToObject(meta,"hardware_odr_hz",200);
    cJSON_AddNumberToObject(meta,"accel_range_g",4);cJSON_AddNumberToObject(meta,"gyro_range_dps",1000);
    cJSON_AddBoolToObject(meta,"configuration_readback",warmup_result==BMI2_OK);
    cJSON_AddNumberToObject(meta,"warmup_result",warmup_result);
    cJSON_AddNumberToObject(meta,"read_errors",read_errors);cJSON_AddNumberToObject(meta,"not_ready",not_ready);
    cJSON_AddNumberToObject(meta,"repeated_sensor_time",repeated);cJSON_AddNumberToObject(meta,"missed_deadlines",missed);
    cJSON_AddNumberToObject(meta,"acquisition_start_us",started);cJSON_AddNumberToObject(meta,"duration_us",ended-started);
    if (cpu_before) cJSON_AddItemToObject(meta,"cpu_before",cpu_before);
    if (cpu_after) cJSON_AddItemToObject(meta,"cpu_after",cpu_after);
    auto* mem=cJSON_AddArrayToObject(meta,"memory_samples");
    for (size_t i=0;i<count/100;++i) {
        const auto& m=memory[i];auto* item=cJSON_CreateObject();
        cJSON_AddNumberToObject(item,"sample_index",(i+1)*100);
        cJSON_AddNumberToObject(item,"free_internal",m.internal);cJSON_AddNumberToObject(item,"free_psram",m.external);
        cJSON_AddNumberToObject(item,"largest_psram",m.largest);cJSON_AddNumberToObject(item,"stack_margin_bytes",m.stack);
        cJSON_AddNumberToObject(item,"free_task_sram",m.sram);cJSON_AddNumberToObject(item,"largest_task_sram",m.largest_sram);
        cJSON_AddItemToArray(mem,item);
    }
    char id[80];snprintf(id,sizeof(id),"%s-imu-baseline",boot_id);
    bool exported=export_diagnostic_capture(id,reinterpret_cast<const uint8_t*>(rows),count*columns*sizeof(int32_t),meta);
    bool ok=exported && count==samples && warmup_result==BMI2_OK && !read_errors && !not_ready && !repeated && !missed;
    free(rows);free(memory);
    diagnostic_check("imu_baseline",ok ? "pass":"fail","6000 checked 100 Hz latest-register polls; independent host cadence assessment required.");
}
