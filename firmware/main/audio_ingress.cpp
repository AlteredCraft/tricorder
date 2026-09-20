#include "audio_ingress.h"
#include "driver/i2s_tdm.h"
#include "esp_attr.h"
#include "freertos/FreeRTOS.h"

static i2s_chan_handle_t observed_rx;
static DRAM_ATTR portMUX_TYPE counter_lock=portMUX_INITIALIZER_UNLOCKED;
static DRAM_ATTR AudioIngressSnapshot counters;

static bool IRAM_ATTR received(i2s_chan_handle_t,i2s_event_data_t* event,void*) {
    portENTER_CRITICAL_ISR(&counter_lock);
    counters.dma_bytes+=event->size;++counters.dma_buffers;
    portEXIT_CRITICAL_ISR(&counter_lock);
    return false;
}
static bool IRAM_ATTR overwritten(i2s_chan_handle_t,i2s_event_data_t* event,void*) {
    portENTER_CRITICAL_ISR(&counter_lock);
    counters.overwritten_bytes+=event->size;++counters.overflows;
    portEXIT_CRITICAL_ISR(&counter_lock);
    return false;
}

extern "C" esp_err_t __real_i2s_channel_init_tdm_mode(i2s_chan_handle_t,const i2s_tdm_config_t*);
extern "C" esp_err_t __wrap_i2s_channel_init_tdm_mode(i2s_chan_handle_t handle,const i2s_tdm_config_t* config) {
    auto result=__real_i2s_channel_init_tdm_mode(handle,config);
    if (result!=ESP_OK) return result;
    // The pinned BSP initializes its sole RX channel in TDM mode while disabled.
    i2s_event_callbacks_t callbacks{};
    callbacks.on_recv=received;callbacks.on_recv_q_ovf=overwritten;
    result=i2s_channel_register_event_callback(handle,&callbacks,nullptr);
    if (result==ESP_OK) observed_rx=handle;
    return result;
}

extern "C" esp_err_t __real_i2s_channel_read(i2s_chan_handle_t,void*,size_t,size_t*,uint32_t);
extern "C" esp_err_t __wrap_i2s_channel_read(i2s_chan_handle_t handle,void* destination,size_t size,size_t* bytes_read,uint32_t timeout_ms) {
    size_t actual=0;
    auto result=__real_i2s_channel_read(handle,destination,size,&actual,timeout_ms);
    if (bytes_read) *bytes_read=actual;
    if (handle!=observed_rx) return result;
    portENTER_CRITICAL(&counter_lock);
    counters.read_bytes+=actual;++counters.read_calls;
    if (actual!=size) ++counters.short_reads;
    if (result!=ESP_OK || actual!=size) ++counters.read_errors;
    portEXIT_CRITICAL(&counter_lock);
    // The codec discards bytes_read; prevent a short read becoming a success.
    return result==ESP_OK && actual!=size ? ESP_FAIL:result;
}

AudioIngressSnapshot audio_ingress_snapshot() {
    portENTER_CRITICAL(&counter_lock);
    auto result=counters;
    portEXIT_CRITICAL(&counter_lock);
    return result;
}

bool begin_audio_epoch(AudioIngressSnapshot& before) {
    if (!observed_rx || i2s_channel_disable(observed_rx)!=ESP_OK) return false;
    before=audio_ingress_snapshot();
    return i2s_channel_enable(observed_rx)==ESP_OK;
}
