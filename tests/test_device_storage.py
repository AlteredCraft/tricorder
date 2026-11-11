"""Exercise the real file commit boundary and credential validation on a host."""
from pathlib import Path
import subprocess
import tempfile
import unittest


class DeviceStorageTests(unittest.TestCase):
    def test_verified_commit_partial_collision_and_config(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            (p/'esp_heap_caps.h').write_text('''#pragma once
#include <cstdlib>
constexpr int MALLOC_CAP_SPIRAM=1,MALLOC_CAP_8BIT=2,MALLOC_CAP_DMA=4,MALLOC_CAP_INTERNAL=8;
extern int requested_caps;extern size_t requested_alignment;
extern bool fail_scratch;
inline void* heap_caps_malloc(size_t n,int caps){requested_caps=caps;return fail_scratch?nullptr:malloc(n);}
inline void* heap_caps_aligned_alloc(size_t a,size_t n,int caps){requested_alignment=a;requested_caps=caps;return fail_scratch?nullptr:aligned_alloc(a,n);}
''')
            (p/'freertos').mkdir()
            (p/'freertos'/'FreeRTOS.h').write_text('''#pragma once
#define pdMS_TO_TICKS(ms) (ms)
extern int delays;
inline void vTaskDelay(int){++delays;}
''')
            (p/'freertos'/'task.h').write_text('#pragma once\n')
            (p/'driver.cpp').write_text(r'''
#include "storage_files.h"
#include <cassert>
#include <cstring>
#include <string>
#include <vector>
#include <unistd.h>
int requested_caps=0;size_t requested_alignment=0;bool fail_scratch=false;int delays=0;
int main(int argc,char** argv) {
 assert(argc==2);std::string root=argv[1];
 const unsigned char data[]={1,0,3,4};
 auto path=root+"/take.raw";
 assert(storage_write_verified(path.c_str(),data,sizeof(data)));
 // SDMMC DMA: an aligned, DMA-capable internal stage, not the PSRAM source.
 assert(requested_caps==(4|8) && requested_alignment==128); // MALLOC_CAP_DMA|MALLOC_CAP_INTERNAL
 assert(!storage_write_verified(path.c_str(),data,sizeof(data)));
 assert(access((path+".part").c_str(),F_OK)!=0);
 auto partial=root+"/interrupted.raw";
 FILE* f=fopen((partial+".part").c_str(),"wb");assert(f);fputc(1,f);fclose(f);
 assert(!storage_write_verified(partial.c_str(),data,sizeof(data)));
 assert(access(partial.c_str(),F_OK)!=0);
 assert(!storage_write_verified((root+"/missing/file").c_str(),data,sizeof(data)));
 std::vector<unsigned char> large(1152000);
 for(size_t i=0;i<large.size();++i)large[i]=(i*37+11)&255;
 delays=0;
 assert(storage_write_verified((root+"/large.raw").c_str(),large.data(),large.size()));
 assert(delays==0);
 fail_scratch=true;
 assert(!storage_write_verified((root+"/no-memory.raw").c_str(),data,sizeof(data)));
 assert(access((root+"/no-memory.raw").c_str(),F_OK)!=0);
 assert(access((root+"/no-memory.raw.part").c_str(),F_OK)!=0); // fails before touching the card
 fail_scratch=false;
 assert(storage_replace_config(root.c_str(),R"({"ssid":"old","password":"one"})"));
 assert(storage_replace_config(root.c_str(),R"({"ssid":"new","password":"two"})"));
 StorageConfig saved{};
 assert(storage_load_config(root.c_str(),saved) && !strcmp(saved.ssid,"new"));
 assert(!storage_replace_config(root.c_str(),"{}"));
 // A power loss between renames leaves the previous valid configuration usable.
 assert(unlink((root+"/wifi.json").c_str())==0);
 assert(storage_load_config(root.c_str(),saved) && !strcmp(saved.ssid,"old"));
 assert(storage_replace_config(root.c_str(),R"({"ssid":"recovered","password":"three"})"));
 assert(storage_load_config(root.c_str(),saved) && !strcmp(saved.ssid,"recovered"));
 f=fopen((root+"/wifi.json").c_str(),"wb");assert(f);fputs("broken",f);fclose(f);
 assert(storage_replace_config(root.c_str(),R"({"ssid":"fixed","password":"four"})"));
 assert(unlink((root+"/wifi.json").c_str())==0);
 assert(storage_load_config(root.c_str(),saved) && !strcmp(saved.ssid,"old"));
 StorageConfig cfg{};
 assert(storage_parse_config(R"({"ssid":"test","password":"password!","endpoint":"ws://192.168.1.2:8765/"})",cfg));
 assert(!strcmp(cfg.ssid,"test") && !strcmp(cfg.password,"password!"));
 for(auto* s:{"{}",R"({"ssid":"","password":"x"})",R"({"ssid":1,"password":"x"})",R"({"ssid":"x","password":null})",R"({"ssid":"x","password":"x","endpoint":"https://x"})",R"({"ssid":"x","password":"x","ssid":"y"})"})assert(!storage_parse_config(s,cfg));
 std::string big="{\"ssid\":\""+std::string(33,'x')+"\",\"password\":\"\"}";
 assert(!storage_parse_config(big.c_str(),cfg));
 // F-0003: hotspot mode. The device broadcasts ssid/password (WPA2: 8-63 bytes); the endpoint is derived.
 assert(storage_parse_config(R"({"ssid":"Tricorder","password":"eight-chars","mode":"ap"})",cfg) && cfg.access_point);
 assert(storage_parse_config(R"({"ssid":"x","password":"","mode":"station"})",cfg) && !cfg.access_point);
 assert(storage_parse_config(R"({"ssid":"x","password":"","endpoint":"ws://192.168.1.2:8765/"})",cfg) && !cfg.access_point);
 for(auto* s:{R"({"ssid":"x","password":"short","mode":"ap"})",R"({"ssid":"x","password":"eight-chars","mode":"mesh"})",
     R"({"ssid":"x","password":"eight-chars","mode":1})",R"({"ssid":"x","password":"eight-chars","mode":"ap","mode":"ap"})"})
  assert(!storage_parse_config(s,cfg));
 // Issue #9: up to four known networks beside the primary one.
 assert(storage_parse_config(R"({"ssid":"Tricorder","password":"eight-chars","mode":"ap","known":[{"ssid":"home","password":"one"},{"ssid":"phone","password":""}]})",cfg));
 assert(cfg.known_count==2 && !strcmp(cfg.known[0].ssid,"home") && !strcmp(cfg.known[0].password,"one") && !strcmp(cfg.known[1].ssid,"phone"));
 StorageConfig other{};
 assert(storage_parse_config(R"({"ssid":"Tricorder","password":"eight-chars","mode":"ap","known":[{"ssid":"home","password":"two"},{"ssid":"phone","password":""}]})",other));
 assert(!storage_config_equal(cfg,other) && storage_config_equal(cfg,cfg));
 assert(storage_parse_config(R"({"ssid":"x","password":"","known":[]})",cfg) && cfg.known_count==0);
 for(auto* s:{R"({"ssid":"x","password":"","known":{}})",R"({"ssid":"x","password":"","known":[{"ssid":"a"}]})",
     R"({"ssid":"x","password":"","known":[{"ssid":"","password":""}]})",R"({"ssid":"x","password":"","known":[{"ssid":"a","password":"","mode":"ap"}]})",
     R"({"ssid":"x","password":"","known":[{"ssid":"a","password":""},{"ssid":"b","password":""},{"ssid":"c","password":""},{"ssid":"d","password":""},{"ssid":"e","password":""}]})"})
  assert(!storage_parse_config(s,cfg));
}
''')
            cjson = Path('.tools/esp-idf/components/json/cJSON')
            for cmd in [
                ['clang', '-fsanitize=address', '-c', str(cjson/'cJSON.c'), '-o', str(p/'json.o')],
                ['clang++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-fsanitize=address',
                 '-DESP_PLATFORM', '-I', str(p), '-I', 'firmware/main', '-I', str(cjson), str(p/'driver.cpp'),
                 'firmware/main/storage_files.cpp', str(p/'json.o'), '-o', str(p/'test')],
                [str(p/'test'), str(p)],
            ]:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
