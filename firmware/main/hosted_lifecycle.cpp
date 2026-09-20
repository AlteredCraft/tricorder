#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

extern "C" esp_err_t __real_esp_hosted_init();

// The pinned hosted component invokes init from a constructor, before the
// scheduler releases startup-stack RAM. Defer that call; network.cpp explicitly
// initializes it from its running task. Runtime calls retain real error results.
extern "C" esp_err_t __wrap_esp_hosted_init() {
    if (xTaskGetSchedulerState() == taskSCHEDULER_NOT_STARTED) return ESP_OK;
    return __real_esp_hosted_init();
}
