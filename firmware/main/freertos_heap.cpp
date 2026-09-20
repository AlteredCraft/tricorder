#include <cstddef>
#include "esp_attr.h"
#include "esp_heap_caps.h"

// IDF 5.4.2's P4 heap permits INTERNAL|8BIT allocations in TCM, while
// xPortcheckValidStackMem rejects that region. Adding the hosted driver exposed
// this in the scheduler's timer-task stack before app_main. Keep FreeRTOS
// allocations in L2 SRAM by requiring SIMD capability (absent in TCM/RTC RAM).
// Do not relax stack validation or modify the pinned vendor checkout.
extern "C" void* IRAM_ATTR __wrap_pvPortMalloc(size_t bytes) {
    return heap_caps_malloc(bytes, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT | MALLOC_CAP_SIMD);
}
