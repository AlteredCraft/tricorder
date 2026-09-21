"""Camera callbacks preserve yield hints and expose hidden backup-buffer use."""
from pathlib import Path
import subprocess
import tempfile
import unittest

class CameraIngressTests(unittest.TestCase):
    def test_buffer_availability_is_not_callback_return_value(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'freertos').mkdir()
            (root/'esp_attr.h').write_text('#define IRAM_ATTR\n#define DRAM_ATTR\n')
            (root/'esp_timer.h').write_text('#include <cstdint>\ninline int64_t esp_timer_get_time() {return 12345;}\n')
            (root/'freertos/FreeRTOS.h').write_text('''#pragma once
using portMUX_TYPE=int;
#define portMUX_INITIALIZER_UNLOCKED 0
#define portENTER_CRITICAL_SAFE(p) ((void)(p))
#define portEXIT_CRITICAL_SAFE(p) ((void)(p))
#define pdMS_TO_TICKS(ms) (ms)
''')
            (root/'esp_cam_ctlr.h').write_text('''#pragma once
#include <cstddef>
using esp_err_t=int;using esp_cam_ctlr_handle_t=void*;
constexpr int ESP_OK=0;
struct esp_cam_ctlr_trans_t {void* buffer;size_t buflen,received_size;};
struct esp_cam_ctlr_evt_cbs_t {
 bool(*on_get_new_trans)(void*,esp_cam_ctlr_trans_t*,void*);
 bool(*on_trans_finished)(void*,esp_cam_ctlr_trans_t*,void*);
};
''')
            (root/'test.cpp').write_text(r'''
#include "camera_ingress.h"
#include "esp_cam_ctlr.h"
#include <cassert>
extern "C" int __wrap_esp_cam_ctlr_register_event_callbacks(void*,const esp_cam_ctlr_evt_cbs_t*,void*);
esp_cam_ctlr_evt_cbs_t installed{};void* context=nullptr;int status=0;
extern "C" int __real_esp_cam_ctlr_register_event_callbacks(void*,const esp_cam_ctlr_evt_cbs_t* callbacks,void* arg) {
 if (status==0 && callbacks) {installed=*callbacks;context=arg;}return status;
}
bool supply=true,yield=false;size_t supplied_size=100;
bool get(void*,esp_cam_ctlr_trans_t* trans,void* arg) {
 assert(arg==reinterpret_cast<void*>(5));
 trans->buffer=supply ? reinterpret_cast<void*>(9):nullptr;trans->buflen=supply ? supplied_size:0;return yield;
}
bool done(void*,esp_cam_ctlr_trans_t*,void* arg) {assert(arg==reinterpret_cast<void*>(5));return true;}
int main() {
 configure_camera_ingress(100);
 esp_cam_ctlr_evt_cbs_t callbacks{get,done};
 status=-7;assert(__wrap_esp_cam_ctlr_register_event_callbacks(nullptr,&callbacks,reinterpret_cast<void*>(5))==-7);
 status=0;assert(__wrap_esp_cam_ctlr_register_event_callbacks(nullptr,&callbacks,reinterpret_cast<void*>(5))==0);
 assert(camera_owns_video(reinterpret_cast<void*>(5)) && !camera_owns_video(nullptr));
 esp_cam_ctlr_trans_t trans{};
 assert(!installed.on_get_new_trans(nullptr,&trans,context));
 auto a=camera_ingress_snapshot();assert(a.requests==1 && a.missing_buffers==0);
 supply=false;yield=true;
 assert(installed.on_get_new_trans(nullptr,&trans,context));
 trans.buffer=reinterpret_cast<void*>(9);trans.received_size=100;assert(installed.on_trans_finished(nullptr,&trans,context));
 a=camera_ingress_snapshot();assert(a.requests==2 && a.missing_buffers==1 && a.finished==1 && a.bytes==100);
 CameraFrameEvidence frame;
 assert(camera_frame_evidence(trans.buffer,frame));
 assert(frame.sequence==1 && frame.finished_us==12345 && frame.bytes==100);
 assert(!camera_frame_evidence(reinterpret_cast<void*>(10),frame));
 assert(__wrap_esp_cam_ctlr_register_event_callbacks(nullptr,&callbacks,reinterpret_cast<void*>(5))==0);
 supply=true;yield=false;assert(!installed.on_get_new_trans(nullptr,&trans,context));
 a=camera_ingress_snapshot();assert(a.requests==3 && a.missing_buffers==1);
 supplied_size=99;installed.on_get_new_trans(nullptr,&trans,context);
 a=camera_ingress_snapshot();assert(a.requests==4 && a.missing_buffers==2);
 // Pinned CSI asks for the NEXT destination before completing the current one.
 // Empty queue: vendor reuses the active destination, then suppresses DONE_BUF.
 assert(__wrap_esp_cam_ctlr_register_event_callbacks(nullptr,&callbacks,reinterpret_cast<void*>(5))==0);
 supplied_size=100;installed.on_get_new_trans(nullptr,&trans,context);
 installed.on_trans_finished(nullptr,&trans,context);
 a=camera_ingress_snapshot();
 assert(a.reused_completions==1 && a.missing_buffers==2);
 // Different next destination means delivery; do not classify it as reuse.
 trans.buffer=reinterpret_cast<void*>(10);
 installed.on_trans_finished(nullptr,&trans,context);
 assert(camera_ingress_snapshot().reused_completions==1);
}
''')
            subprocess.run(['clang++','-std=c++17','-Wall','-Wextra','-Werror','-I',str(root),'-I','firmware/main',
                            str(root/'test.cpp'),'firmware/main/camera_ingress.cpp','-o',str(root/'test')],check=True,capture_output=True)
            subprocess.run([str(root/'test')],check=True)
