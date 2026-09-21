"""The pinned driver's failed force-end must not unwind a live DMA descriptor."""
from pathlib import Path
import subprocess
import tempfile
import unittest


class JpegGuardTests(unittest.TestCase):
    def test_driver_timeout_stops_before_stack_and_source_lifetimes_end(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for folder in ('driver','freertos','esp_private'):(root/folder).mkdir()
            (root/'driver/jpeg_encode.h').write_text('''#pragma once
#include <cstdint>
using esp_err_t=int;using jpeg_encoder_handle_t=void*;
constexpr int ESP_OK=0,ESP_ERR_INVALID_STATE=259,ESP_ERR_TIMEOUT=263;
struct jpeg_encode_cfg_t {};
esp_err_t jpeg_encoder_process(void*,const jpeg_encode_cfg_t*,const uint8_t*,uint32_t,uint8_t*,uint32_t,uint32_t*);
''')
            (root/'freertos/FreeRTOS.h').write_text('#pragma once\nusing TaskHandle_t=void*;\n')
            (root/'freertos/task.h').write_text('''#pragma once
#include "FreeRTOS.h"
extern TaskHandle_t current_task;
inline TaskHandle_t xTaskGetCurrentTaskHandle() {return current_task;}
extern bool in_isr;
inline bool xPortInIsrContext() {return in_isr;}
''')
            (root/'esp_private/dma2d.h').write_text('#pragma once\nstruct dma2d_trans_t {};\n')
            (root/'esp_system.h').write_text('#pragma once\n[[noreturn]] void esp_system_abort(const char*);\n')
            (root/'test.cpp').write_text(r'''
#include "jpeg_guard.h"
#include "freertos/task.h"
#include "esp_private/dma2d.h"
#include <cassert>
#include <cstdlib>
#include <cstring>
TaskHandle_t current_task=reinterpret_cast<void*>(1);bool in_isr=false;
int mode=0,force_calls=0;bool pending=false,driver_stack_live=false;
const uint8_t* source=nullptr;
extern "C" int __wrap_dma2d_force_end(dma2d_trans_t*,bool*);
extern "C" int __real_dma2d_force_end(dma2d_trans_t*,bool*) {
 ++force_calls;return ESP_ERR_INVALID_STATE; // Queued job remains queued.
}
[[noreturn]] void esp_system_abort(const char* reason) {
 assert(strstr(reason,"JPEG DMA ownership") && pending && driver_stack_live);
 assert(force_calls==0 && source && *source==77);
 std::_Exit(42); // Verify the guard fires BEFORE vendor error-path unwinding.
}
int jpeg_encoder_process(void*,const jpeg_encode_cfg_t*,const uint8_t* raw,uint32_t,uint8_t*,uint32_t,uint32_t*) {
 if (mode==0) return ESP_OK;
 if (mode==1) return -7; // Parameter/header failure before enqueue is safe.
 source=raw;pending=true;driver_stack_live=true;
 dma2d_trans_t descriptor;bool yield=false;
 if (mode==3) current_task=reinterpret_cast<void*>(2);
 if (mode==4) in_isr=true;
 if (mode==5) {
  mode=0;
  assert(jpeg_encode_guarded(nullptr,nullptr,raw,1,nullptr,0,nullptr)==ESP_ERR_INVALID_STATE);
  mode=5;driver_stack_live=false;return ESP_OK;
 }
 // Replays jpeg_encode.c's err1 path: stop result is discarded, then the
 // function returns while a pending descriptor still refers to local data.
 __wrap_dma2d_force_end(&descriptor,&yield);
 current_task=reinterpret_cast<void*>(1);in_isr=false;
 driver_stack_live=false;
 return ESP_ERR_TIMEOUT;
}
int main(int argc,char** argv) {
 assert(argc==2);uint8_t raw=77;mode=std::atoi(argv[1]);
 if (mode==6) {
  mode=2;
  assert(jpeg_encoder_process(nullptr,nullptr,&raw,1,nullptr,0,nullptr)==ESP_ERR_TIMEOUT);
  assert(pending && !driver_stack_live && force_calls==1); // Original hazard.
  return 0;
 }
 const int expected=mode==1 ? -7 : (mode==3 || mode==4 ? ESP_ERR_TIMEOUT:ESP_OK);
 assert(jpeg_encode_guarded(nullptr,nullptr,&raw,1,nullptr,0,nullptr)==expected);
 // Successful/early-error return must clear the task guard for other users.
 const int previous=force_calls;dma2d_trans_t trans;bool yield=false;
 assert(__wrap_dma2d_force_end(&trans,&yield)==ESP_ERR_INVALID_STATE);
 assert(force_calls==previous+1);
}
''')
            result=subprocess.run(['clang++','-std=c++17','-Wall','-Wextra','-Werror',
                                   '-I',str(root),'-I','firmware/main',str(root/'test.cpp'),
                                   'firmware/main/jpeg_guard.cpp','-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            for mode in range(7):
                result=subprocess.run([str(root/'test'),str(mode)],capture_output=True,text=True)
                self.assertEqual(result.returncode,42 if mode==2 else 0,(mode,result.stderr))
