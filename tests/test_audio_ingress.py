"""Fault-inject the actual I2S instrumentation wrappers without hardware."""
from pathlib import Path
import subprocess
import tempfile
import unittest


class AudioIngressTests(unittest.TestCase):
    def test_actual_byte_counts_overflow_and_lifecycle_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'driver').mkdir();(root/'freertos').mkdir()
            (root/'esp_attr.h').write_text('#define IRAM_ATTR\n#define DRAM_ATTR\n')
            (root/'freertos/FreeRTOS.h').write_text('''#pragma once
typedef int portMUX_TYPE;
#define portMUX_INITIALIZER_UNLOCKED 0
#define portENTER_CRITICAL(p) ((void)(p))
#define portEXIT_CRITICAL(p) ((void)(p))
#define portENTER_CRITICAL_ISR(p) ((void)(p))
#define portEXIT_CRITICAL_ISR(p) ((void)(p))
''')
            (root/'driver/i2s_tdm.h').write_text('''#pragma once
#include <cstddef>
#include <cstdint>
using esp_err_t=int; using i2s_chan_handle_t=void*;
constexpr int ESP_OK=0,ESP_FAIL=-1;
struct i2s_tdm_config_t {};
struct i2s_event_data_t { size_t size; };
using callback_t=bool(*)(i2s_chan_handle_t,i2s_event_data_t*,void*);
struct i2s_event_callbacks_t { callback_t on_recv{},on_recv_q_ovf{},on_sent{},on_send_q_ovf{}; };
extern "C" int i2s_channel_register_event_callback(void*,const i2s_event_callbacks_t*,void*);
extern "C" int i2s_channel_disable(void*);
extern "C" int i2s_channel_enable(void*);
''')
            (root/'test.cpp').write_text(r'''
#include "audio_ingress.h"
#include "driver/i2s_tdm.h"
#include <cassert>
extern "C" int __wrap_i2s_channel_init_tdm_mode(void*,const i2s_tdm_config_t*);
extern "C" int __wrap_i2s_channel_read(void*,void*,size_t,size_t*,uint32_t);
i2s_event_callbacks_t callbacks;
int init_result=0,register_result=0,read_result=0,disable_result=0,enable_result=0;
size_t actual=8;int disables=0,enables=0;
extern "C" int __real_i2s_channel_init_tdm_mode(void*,const i2s_tdm_config_t*) {return init_result;}
extern "C" int i2s_channel_register_event_callback(void*,const i2s_event_callbacks_t* cb,void*) {callbacks=*cb;return register_result;}
extern "C" int __real_i2s_channel_read(void*,void*,size_t,size_t* count,uint32_t) {*count=actual;return read_result;}
extern "C" int i2s_channel_disable(void*) {++disables;return disable_result;}
extern "C" int i2s_channel_enable(void*) {++enables;return enable_result;}
int main() {
    AudioIngressSnapshot before;
    assert(!begin_audio_epoch(before));
    void* rx=reinterpret_cast<void*>(1);i2s_tdm_config_t config;
    init_result=-3;assert(__wrap_i2s_channel_init_tdm_mode(rx,&config)==-3);
    init_result=0;register_result=-4;assert(__wrap_i2s_channel_init_tdm_mode(rx,&config)==-4);
    assert(!begin_audio_epoch(before));
    register_result=0;assert(__wrap_i2s_channel_init_tdm_mode(rx,&config)==0);
    i2s_event_data_t event{1920};
    callbacks.on_recv(rx,&event,nullptr);callbacks.on_recv_q_ovf(rx,&event,nullptr);
    assert(begin_audio_epoch(before));assert(disables==1 && enables==1);
    assert(before.dma_bytes==1920 && before.overwritten_bytes==1920 && before.overflows==1);
    char output[8];size_t count=0;
    assert(__wrap_i2s_channel_read(rx,output,8,&count,100)==0 && count==8);
    actual=4;assert(__wrap_i2s_channel_read(rx,output,8,&count,100)==ESP_FAIL && count==4);
    read_result=-5;actual=2;assert(__wrap_i2s_channel_read(rx,output,8,&count,100)==-5 && count==2);
    auto after=audio_ingress_snapshot();
    assert(after.read_bytes==14 && after.read_calls==3 && after.short_reads==2 && after.read_errors==2);
    disable_result=-6;assert(!begin_audio_epoch(before));assert(enables==1);
    disable_result=0;enable_result=-7;assert(!begin_audio_epoch(before));
}
''')
            subprocess.run(['clang++','-std=c++17','-Wall','-Wextra','-Werror','-I',str(root),
                            '-I','firmware/main',str(root/'test.cpp'),'firmware/main/audio_ingress.cpp',
                            '-o',str(root/'test')],check=True,capture_output=True)
            subprocess.run([str(root/'test')],check=True)
