#include "ui_ingress.h"
#include "ui_schedule.h"
#include "diagnostic_events.h"
#include "workload_metrics.h"
#include "media.h"
#include "bsp/m5stack_tab5.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <cstdio>
#include <cstdlib>

struct UiMemory {size_t internal,external,largest,stack,sram,largest_sram;};
struct UiAnimation {
    UiIngress* ingress;
    lv_obj_t* tile;
    lv_obj_t* label;
    UiSchedule schedule;
    uint64_t generation=0;
};
static void animate(UiAnimation& context) {
    ++context.generation;
    const auto changed=esp_timer_get_time();
    lv_obj_set_x(context.tile,280+(context.generation*7)%800);
    lv_obj_set_style_bg_color(context.tile,lv_color_hex(context.generation%2 ? 0x24C8BC:0x297CD8),0);
    lv_label_set_text_fmt(context.label,"Frame %lu",static_cast<unsigned long>(context.generation));
    context.ingress->animation(context.generation,changed);
}
static void animation_tick(lv_timer_t* timer) {
    auto& context=*static_cast<UiAnimation*>(lv_timer_get_user_data(timer));
    animate(context);
    lv_timer_set_period(timer,context.schedule.after_tick(esp_timer_get_time()));
}
static void observe_display(lv_event_t* event) {
    auto& context=*static_cast<UiAnimation*>(lv_event_get_user_data(event));
    auto* display=lv_display_get_default();
    switch (lv_event_get_code(event)) {
        case LV_EVENT_RENDER_START:context.ingress->render();break;
        case LV_EVENT_FLUSH_START:context.ingress->flush(lv_display_flush_is_last(display));break;
        default:break;
    }
}

void run_ui_baseline(const char* boot_id) {
    constexpr size_t capacity=8192;
    auto* rows=static_cast<UiSubmissionRow*>(heap_caps_malloc(capacity*sizeof(UiSubmissionRow),MALLOC_CAP_SPIRAM));
    auto* memory=static_cast<UiMemory*>(calloc(60,sizeof(UiMemory)));
    if (!rows || !memory) {
        free(rows);free(memory);diagnostic_check("ui_baseline","fail","UI evidence allocation failed.");return;
    }
    diagnostic_stage("DISPLAY BASELINE / 60 seconds\n\nAutomatic animation and panel-submission timing.\nNo touch interaction is needed.");
    configASSERT(bsp_display_lock(0));
    auto* display=lv_display_get_default();
    auto* tile=lv_obj_create(lv_screen_active());
    lv_obj_set_size(tile,128,80);lv_obj_set_pos(tile,280,500);
    auto* label=lv_label_create(tile);lv_obj_center(label);lv_label_set_text(label,"Starting");
    lv_refr_now(display); // Settle the new objects before the measured epoch.
    bsp_display_unlock();
    vTaskDelay(pdMS_TO_TICKS(100));
    auto* cpu_before=workload_cpu_snapshot();
    configASSERT(bsp_display_lock(0));
    const int64_t started=esp_timer_get_time();
    UiIngress log(rows,capacity,started);
    UiAnimation context{&log,tile,label,UiSchedule(started)};
    lv_timer_set_period(lv_display_get_refr_timer(display),20);
    lv_display_add_event_cb(display,observe_display,LV_EVENT_ALL,&context);
    ui_observe(&log);
    animate(context);
    auto* timer=lv_timer_create(animation_tick,33,&context);
    configASSERT(timer);
    bsp_display_unlock();
    TickType_t wake=xTaskGetTickCount();
    for (size_t second=0;second<60;++second) {
        vTaskDelayUntil(&wake,pdMS_TO_TICKS(1000));
        auto& m=memory[second];
        m.internal=heap_caps_get_free_size(MALLOC_CAP_INTERNAL);m.external=heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
        m.largest=heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM);m.stack=uxTaskGetStackHighWaterMark(nullptr);
        constexpr auto caps=MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT|MALLOC_CAP_SIMD;
        m.sram=heap_caps_get_free_size(caps);m.largest_sram=heap_caps_get_largest_free_block(caps);
    }
    // Round the sample window up to a full 60 seconds despite tick phase.
    if (esp_timer_get_time()-started<60000000) vTaskDelay(pdMS_TO_TICKS(1));
    configASSERT(bsp_display_lock(0));
    lv_timer_delete(timer);
    lv_refr_now(display); // Submit the final changed state before removing observers.
    const int64_t ended=esp_timer_get_time();
    ui_observe(nullptr);
    lv_display_remove_event_cb_with_user_data(display,observe_display,&context);
    lv_timer_set_period(lv_display_get_refr_timer(display),LV_DEF_REFR_PERIOD);
    lv_obj_delete(tile);
    bsp_display_unlock();
    auto* cpu_after=workload_cpu_snapshot();
    auto* meta=diagnostic_event("capture_start");
    cJSON_AddStringToObject(meta,"format","ui_baseline_i64le");
    cJSON_AddStringToObject(meta,"layout","render,generation,changed_us,submitted_us,returned_us,x1,y1,x2,y2,result,last_flush; device times relative to epoch; physical panel coordinates");
    cJSON_AddStringToObject(meta,"policy","latest animation state per render; coalesced generations counted by host");
    cJSON_AddNumberToObject(meta,"rows",log.count());cJSON_AddNumberToObject(meta,"columns",11);
    cJSON_AddNumberToObject(meta,"animation_period_ms",33);
    cJSON_AddNumberToObject(meta,"refresh_period_ms",20);
    cJSON_AddNumberToObject(meta,"missed_animation_deadlines",context.schedule.missed());cJSON_AddNumberToObject(meta,"tile_width",128);cJSON_AddNumberToObject(meta,"tile_height",80);
    cJSON_AddNumberToObject(meta,"generations",context.generation);cJSON_AddNumberToObject(meta,"renders",log.renders());
    cJSON_AddNumberToObject(meta,"submissions",log.submissions());cJSON_AddNumberToObject(meta,"observer_overflow",log.overflow());
    cJSON_AddNumberToObject(meta,"duration_us",ended-started);cJSON_AddNumberToObject(meta,"acquisition_start_us",started);
    if (cpu_before) cJSON_AddItemToObject(meta,"cpu_before",cpu_before);
    if (cpu_after) cJSON_AddItemToObject(meta,"cpu_after",cpu_after);
    auto* mem=cJSON_AddArrayToObject(meta,"memory_samples");
    for (size_t i=0;i<60;++i) {
        const auto& m=memory[i];auto* item=cJSON_CreateObject();
        cJSON_AddNumberToObject(item,"second",i+1);
        cJSON_AddNumberToObject(item,"free_internal",m.internal);cJSON_AddNumberToObject(item,"free_psram",m.external);
        cJSON_AddNumberToObject(item,"largest_psram",m.largest);cJSON_AddNumberToObject(item,"stack_margin_bytes",m.stack);
        cJSON_AddNumberToObject(item,"free_task_sram",m.sram);cJSON_AddNumberToObject(item,"largest_task_sram",m.largest_sram);
        cJSON_AddItemToArray(mem,item);
    }
    char id[80];snprintf(id,sizeof(id),"%s-ui-baseline",boot_id);
    bool exported=log.count() && export_diagnostic_capture(id,reinterpret_cast<const uint8_t*>(rows),log.count()*sizeof(UiSubmissionRow),meta);
    if (!log.count()) cJSON_Delete(meta);
    bool ok=exported && !context.schedule.missed() && !log.overflow() && log.renders()>0 && ended-started>=60000000;
    free(rows);free(memory);
    diagnostic_check("ui_baseline",ok ? "pass":"fail","60-second animation-to-panel submissions; independent host cadence assessment required.");
}
