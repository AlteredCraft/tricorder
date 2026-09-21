"""Pinned video lists push at the head; acquisition must pop the oldest completion."""
from pathlib import Path
import subprocess
import tempfile
import unittest


class CameraReceiveTests(unittest.TestCase):
    def test_fifo_timeout_and_other_device_delegation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'esp_video.h').write_text(r'''
#pragma once
#include <cstdint>
#include <sys/queue.h>
#include <cassert>
enum v4l2_buf_type {V4L2_BUF_TYPE_VIDEO_CAPTURE=1,V4L2_BUF_TYPE_VIDEO_OUTPUT=2};
struct esp_video_buffer_element {bool free=false;unsigned id;SLIST_ENTRY(esp_video_buffer_element) node;};
SLIST_HEAD(elements,esp_video_buffer_element);
struct esp_video_stream {elements done_list{};int ready_sem=0;};
struct esp_video {int stream_lock=0;esp_video_stream stream;};
inline esp_video_stream* esp_video_get_stream(esp_video* v,v4l2_buf_type t) {
 return t==V4L2_BUF_TYPE_VIDEO_CAPTURE ? &v->stream:nullptr;
}
extern unsigned waited;extern bool ready;
inline int xSemaphoreTake(int,unsigned ticks) {waited=ticks;return ready;}
constexpr int pdTRUE=1;
#define pdMS_TO_TICKS(n) (n)
#define portENTER_CRITICAL_SAFE(p) assert(++*(p)==1)
#define portEXIT_CRITICAL_SAFE(p) assert(--*(p)==0)
#define ELEMENT_SET_FREE(p) ((p)->free=true)
''')
            (root/'test.cpp').write_text(r'''
#include "esp_video.h"
#include "camera_ingress.h"
unsigned waited=0,delegated=0;bool ready=true;
esp_video owner;
bool camera_owns_video(const void* video) {return video==&owner;}
extern "C" esp_video_buffer_element* __real_esp_video_recv_element(esp_video*,uint32_t,uint32_t ticks) {
 ++delegated;waited=ticks;return nullptr;
}
extern "C" esp_video_buffer_element* __wrap_esp_video_recv_element(esp_video*,uint32_t,uint32_t);
int main() {
 esp_video_buffer_element a{false,1,{}},b{false,2,{}},c{false,3,{}};
 for(auto* item:{&a,&b,&c}) SLIST_INSERT_HEAD(&owner.stream.done_list,item,node);
 ready=false;assert(!__wrap_esp_video_recv_element(&owner,1,0xffffffff));
 assert(waited==2000 && !a.free && !b.free && !c.free);
 ready=true;
 assert(__wrap_esp_video_recv_element(&owner,1,30)==&a && a.free && waited==30);
 assert(__wrap_esp_video_recv_element(&owner,1,0)==&b && b.free && waited==0);
 assert(__wrap_esp_video_recv_element(&owner,1,30)==&c && c.free);
 assert(!__wrap_esp_video_recv_element(&owner,1,30));
 assert(!__wrap_esp_video_recv_element(&owner,2,30) && delegated==1);
 esp_video other;assert(!__wrap_esp_video_recv_element(&other,1,9999));
 assert(delegated==2 && waited==2000 && owner.stream_lock==0);
}
''')
            # Include initializer_list explicitly for the short range fixtures.
            subprocess.run(['clang++','-std=c++17','-Wall','-Wextra','-Werror','-include','initializer_list',
                            '-I',str(root),'-I','firmware/main',str(root/'test.cpp'),
                            'firmware/main/camera_receive.cpp','-o',str(root/'test')],check=True,capture_output=True)
            subprocess.run([str(root/'test')],check=True)
