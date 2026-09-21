#include "jpeg_guard.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_private/dma2d.h"
#include "esp_system.h"
#include <atomic>

static std::atomic<TaskHandle_t> encoder_task{nullptr};

esp_err_t jpeg_encode_guarded(jpeg_encoder_handle_t engine,const jpeg_encode_cfg_t* config,
                              const uint8_t* source,uint32_t source_bytes,uint8_t* output,
                              uint32_t output_capacity,uint32_t* output_bytes) {
    TaskHandle_t expected=nullptr;
    if (!encoder_task.compare_exchange_strong(expected,xTaskGetCurrentTaskHandle())) return ESP_ERR_INVALID_STATE;
    auto result=jpeg_encoder_process(engine,config,source,source_bytes,output,output_capacity,output_bytes);
    encoder_task.store(nullptr);
    return result;
}

extern "C" esp_err_t __real_dma2d_force_end(dma2d_trans_t*,bool*);
extern "C" esp_err_t __wrap_dma2d_force_end(dma2d_trans_t* trans,bool* yield) {
    const auto owner=encoder_task.load();
    if (owner && !xPortInIsrContext() && owner==xTaskGetCurrentTaskHandle()) {
        // Pinned jpeg_encode.c's err1 path discards force_end's result. A
        // queued transaction may still reference its stack-local descriptor;
        // on reuse, its rx_chan may even identify another client's channel.
        // Abort BEFORE that path returns, retries, or touches a stale channel.
        // This is a recorded failed boot, not successful timeout recovery.
        esp_system_abort("JPEG DMA ownership unresolved: refusing error-path release");
    }
    return __real_dma2d_force_end(trans,yield);
}
