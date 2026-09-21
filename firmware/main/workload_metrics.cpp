#include "workload_metrics.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <cstdlib>

cJSON* workload_cpu_snapshot() {
    constexpr unsigned capacity=64;
    auto* tasks=static_cast<TaskStatus_t*>(malloc(capacity*sizeof(TaskStatus_t)));
    if (!tasks) return nullptr;
    configRUN_TIME_COUNTER_TYPE total=0;
    unsigned count=uxTaskGetSystemState(tasks,capacity,&total);
    auto* result=cJSON_CreateObject();
    cJSON_AddNumberToObject(result,"total_ticks",total);
    auto* list=cJSON_AddArrayToObject(result,"tasks");
    for (unsigned i=0;i<count;++i) {
        auto* task=cJSON_CreateObject();
        cJSON_AddNumberToObject(task,"id",tasks[i].xTaskNumber);
        cJSON_AddStringToObject(task,"name",tasks[i].pcTaskName);
        cJSON_AddNumberToObject(task,"ticks",tasks[i].ulRunTimeCounter);
        cJSON_AddNumberToObject(task,"stack_margin_bytes",tasks[i].usStackHighWaterMark);
        cJSON_AddNumberToObject(task,"core_affinity",tasks[i].xCoreID);
        cJSON_AddNumberToObject(task,"base_priority",tasks[i].uxBasePriority);
        cJSON_AddItemToArray(list,task);
    }
    free(tasks);return result;
}
