#include "jpeg_timeout_fixture.h"
#include "sdkconfig.h"
#if CONFIG_TRICORDER_JPEG_QUEUE_TIMEOUT_FIXTURE
#include "esp_private/dma2d.h"
#include "esp_attr.h"
#include "esp_heap_caps.h"
#include "esp_system.h"
#include "diagnostic_events.h"
#include <atomic>

static RTC_NOINIT_ATTR uint32_t exercised;
static std::atomic<bool> acquired{false};
static dma2d_pool_handle_t pool=nullptr;
static dma2d_trans_config_t blocker{};
static bool picked(uint32_t,const dma2d_trans_channel_info_t*,void*) {
    acquired.store(true);
    // Hold assigned channels without starting a hardware transfer. P4 has one
    // TX reorder channel; JPEG's real transaction must wait in the pool queue.
    return false;
}
bool jpeg_arm_queue_timeout_fixture() {
    constexpr uint32_t marker=0x4a514631;
    if (esp_reset_reason()==ESP_RST_PANIC && exercised==marker) {
        diagnostic_check("jpeg_timeout_fixture_skipped","pass","Expected panic reboot; fixture is not rearmed.");
        return false;
    }
    exercised=marker;
    dma2d_pool_config_t config{};config.pool_id=0;
    auto* transaction=static_cast<dma2d_trans_t*>(heap_caps_calloc(1,SIZEOF_DMA2D_TRANS_T,MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT));
    if (!transaction || dma2d_acquire_pool(&config,&pool)!=ESP_OK)
        esp_system_abort("JPEG fixture initialization failed");
    blocker.tx_channel_num=1;blocker.rx_channel_num=1;
    blocker.channel_flags=DMA2D_CHANNEL_FUNCTION_FLAG_TX_REORDER;blocker.on_job_picked=picked;
    if (dma2d_enqueue(pool,&blocker,transaction)!=ESP_OK || !acquired.load())
        esp_system_abort("JPEG fixture did not reserve the reorder channel");
    diagnostic_check("jpeg_timeout_fixture_armed","pass","Reorder channel held without DMA; next real JPEG must queue and time out.");
    return true;
}
#else
bool jpeg_arm_queue_timeout_fixture() {return false;}
#endif
