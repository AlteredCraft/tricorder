"""Exercise actual pipeline construction, worker shutdown and bounded retention."""
from pathlib import Path
import subprocess
import tempfile
import unittest


class JpegPipelineTests(unittest.TestCase):
    def test_partial_failures_worker_lifetime_and_retention_exhaustion(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for header in ('driver/jpeg_encode.h','esp_heap_caps.h','esp_timer.h','freertos/FreeRTOS.h',
                           'freertos/task.h','freertos/semphr.h','mbedtls/sha256.h','cJSON.h'):
                path=root/header;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('#pragma once\n')
            (root/'test.cpp').write_text(r'''
#include "jpeg_pipeline_environment.h"
#define free host_free
#include "jpeg_pipeline.cpp"
#undef free
void clean() {
 join_workers();assert(allocations.empty() && live_semaphores==0 && live_engines==0);
}
int main() {
 for (unsigned failure=1;failure<=7;++failure) {
  allocation_step=0;fail_step=failure;
  {JpegPipeline p(16,16);assert(!p.ready());}
  clean();
 }
 fail_step=0;allocation_step=0;
 {JpegPipeline invalid(0,720);assert(!invalid.ready());}
 assert(allocation_step==0);clean();
 for (unsigned cycle=0;cycle<10;++cycle) {
  exported_images=0;
  {JpegPipeline p(16,16);assert(p.ready());p.begin(1);
   uint8_t source[512];std::memset(source,77,sizeof(source));
   for(unsigned frame=1;frame<=30;++frame) {
    CameraFrameEvidence evidence{frame,esp_timer_get_time(),sizeof(source)};
    assert(p.submit(source,sizeof(source),evidence,esp_timer_get_time()));p.dispatch();
    std::memset(source,frame,sizeof(source)); // Camera may reuse its buffer now.
    p.wait_idle();
   }
   assert(p.export_results("host") && exported_images==30);
  }
  clean();
 }
 // Both post-encode source damage and a safe pre-enqueue codec error must fail
 // export, while still returning the copied slot and cleaning every resource.
 for (unsigned failure=0;failure<2;++failure) {
  damage_source=failure==0;codec_result=failure==1 ? ESP_FAIL:ESP_OK;
  {JpegPipeline p(16,16);uint8_t source[512]{};
   CameraFrameEvidence evidence{1,1,sizeof(source)};
   assert(p.submit(source,sizeof(source),evidence,1));p.dispatch();p.wait_idle();
   assert(!p.export_results("host"));
  }
  clean();
 }
 damage_source=false;codec_result=ESP_OK;encoded_bytes=500000;exported_images=0;
 {JpegPipeline p(512,512);std::vector<uint8_t> source(512*512*2,77);
  for(unsigned frame=1;frame<=30;++frame) {
   CameraFrameEvidence evidence{frame,1,source.size()};
   assert(p.submit(source.data(),source.size(),evidence,1));p.dispatch();p.wait_idle();
  }
  assert(!p.export_results("host") && exported_images==12); // 6 MiB cap.
 }
 clean();
 // Destruction with a running job cannot delete its engine or source/output.
 encoded_bytes=100;hold_codec.store(true);
 auto* active=new JpegPipeline(16,16);uint8_t source[512]{};
 CameraFrameEvidence evidence{1,1,sizeof(source)};
 assert(active->submit(source,sizeof(source),evidence,1));active->dispatch();
 while (!codec_live.load()) std::this_thread::yield();
 std::atomic<bool> destroy_entered{false},destroy_returned{false};
 std::thread destroyer([&]{destroy_entered.store(true);delete active;destroy_returned.store(true);});
 while (!destroy_entered.load()) std::this_thread::yield();
 std::this_thread::sleep_for(std::chrono::milliseconds(20));
 assert(!destroy_returned.load());
 hold_codec.store(false);destroyer.join();assert(destroy_returned.load());clean();
}
''')
            result=subprocess.run(['clang++','-std=c++17','-O1','-pthread','-fsanitize=address',
                                   '-Wall','-Wextra','-Werror','-I',str(root),'-I','tests','-I','firmware/main',
                                   str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(root/'test')],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
