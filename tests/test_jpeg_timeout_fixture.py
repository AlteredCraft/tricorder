"""The opt-in hardware fixture reserves the sole reorder channel without DMA."""
from pathlib import Path
import subprocess
import tempfile
import unittest


class JpegTimeoutFixtureTests(unittest.TestCase):
    def test_fixture_blocks_real_queue_and_skips_after_its_panic(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'esp_private').mkdir()
            (root/'esp_private/dma2d.h').write_text('''#pragma once
#include <cstdint>
using dma2d_pool_handle_t=void*;
struct dma2d_trans_t {int value;};
struct dma2d_pool_config_t {unsigned pool_id;};
struct dma2d_trans_channel_info_t {};
struct dma2d_trans_config_t {
 unsigned tx_channel_num=0,rx_channel_num=0,channel_flags=0;
 bool(*on_job_picked)(uint32_t,const dma2d_trans_channel_info_t*,void*)=nullptr;
 void* user_config=nullptr;
};
constexpr unsigned DMA2D_CHANNEL_FUNCTION_FLAG_TX_REORDER=1;
#define SIZEOF_DMA2D_TRANS_T sizeof(dma2d_trans_t)
constexpr int ESP_OK=0;
int dma2d_acquire_pool(const dma2d_pool_config_t*,dma2d_pool_handle_t*);
int dma2d_enqueue(dma2d_pool_handle_t,const dma2d_trans_config_t*,dma2d_trans_t*);
''')
            (root/'esp_attr.h').write_text('#define RTC_NOINIT_ATTR\n')
            (root/'esp_heap_caps.h').write_text('''#include <cstdlib>
#define MALLOC_CAP_INTERNAL 1
#define MALLOC_CAP_8BIT 2
inline void* heap_caps_calloc(size_t a,size_t b,int) {return calloc(a,b);}
''')
            (root/'esp_system.h').write_text('''#pragma once
constexpr int ESP_RST_PANIC=4;
extern int reason;
inline int esp_reset_reason() {return reason;}
[[noreturn]] void esp_system_abort(const char*);
''')
            (root/'cJSON.h').write_text('struct cJSON;\n')
            (root/'sdkconfig.h').write_text('#define CONFIG_TRICORDER_JPEG_QUEUE_TIMEOUT_FIXTURE 1\n')
            (root/'test.cpp').write_text(r'''
#include "esp_private/dma2d.h"
#include "jpeg_timeout_fixture.h"
#include "esp_system.h"
#include <cassert>
#include <cstdlib>
#include <cstring>
int reason=0,acquires=0,enqueues=0;const dma2d_trans_config_t* saved=nullptr;dma2d_trans_t* allocation=nullptr;
int dma2d_acquire_pool(const dma2d_pool_config_t* config,dma2d_pool_handle_t* pool) {
 assert(config->pool_id==0);++acquires;*pool=reinterpret_cast<void*>(1);return ESP_OK;
}
int dma2d_enqueue(dma2d_pool_handle_t pool,const dma2d_trans_config_t* config,dma2d_trans_t* trans) {
 assert(pool && trans && config->tx_channel_num==1 && config->rx_channel_num==1);
 assert(config->channel_flags==DMA2D_CHANNEL_FUNCTION_FLAG_TX_REORDER);
 ++enqueues;saved=config;allocation=trans;
 assert(!config->on_job_picked(2,nullptr,config->user_config));return ESP_OK;
}
void diagnostic_check(const char*,const char* status,const char*) {assert(!strcmp(status,"pass"));}
[[noreturn]] void esp_system_abort(const char*) {std::abort();}
int main() {
 assert(jpeg_arm_queue_timeout_fixture());assert(acquires==1 && enqueues==1);
 // Descriptor/callback context remains valid after the setup function returns.
 assert(saved && !saved->on_job_picked(2,nullptr,saved->user_config));
 reason=ESP_RST_PANIC;
 assert(!jpeg_arm_queue_timeout_fixture());assert(acquires==1 && enqueues==1);
 free(allocation);
}
''')
            result=subprocess.run(['clang++','-std=c++17','-Wall','-Wextra','-Werror',
                                   '-I',str(root),'-I','firmware/main',str(root/'test.cpp'),
                                   'firmware/main/jpeg_timeout_fixture.cpp','-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            subprocess.run([str(root/'test')],check=True)
