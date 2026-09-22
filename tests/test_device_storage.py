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
constexpr int MALLOC_CAP_SPIRAM=1,MALLOC_CAP_8BIT=2;
extern int requested_caps;
extern bool fail_scratch;
inline void* heap_caps_malloc(size_t n,int caps){requested_caps=caps;return fail_scratch?nullptr:malloc(n);}
''')
            (p/'driver.cpp').write_text(r'''
#include "storage_files.h"
#include <cassert>
#include <cstring>
#include <string>
#include <vector>
#include <unistd.h>
int requested_caps=0;bool fail_scratch=false;
int main(int argc,char** argv) {
 assert(argc==2);std::string root=argv[1];
 const unsigned char data[]={1,0,3,4};
 auto path=root+"/take.raw";
 assert(storage_write_verified(path.c_str(),data,sizeof(data)));
 assert(requested_caps==3);
 assert(!storage_write_verified(path.c_str(),data,sizeof(data)));
 assert(access((path+".part").c_str(),F_OK)!=0);
 auto partial=root+"/interrupted.raw";
 FILE* f=fopen((partial+".part").c_str(),"wb");assert(f);fputc(1,f);fclose(f);
 assert(!storage_write_verified(partial.c_str(),data,sizeof(data)));
 assert(access(partial.c_str(),F_OK)!=0);
 assert(!storage_write_verified((root+"/missing/file").c_str(),data,sizeof(data)));
 std::vector<unsigned char> large(1152000);
 for(size_t i=0;i<large.size();++i)large[i]=(i*37+11)&255;
 assert(storage_write_verified((root+"/large.raw").c_str(),large.data(),large.size()));
 fail_scratch=true;
 assert(!storage_write_verified((root+"/no-memory.raw").c_str(),data,sizeof(data)));
 assert(access((root+"/no-memory.raw").c_str(),F_OK)!=0);
 assert(access((root+"/no-memory.raw.part").c_str(),F_OK)==0);
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
 assert(storage_public_name("ab-123-a.raw"));
 assert(storage_public_name("ab-123-a.json"));
 for(auto* s:{"../wifi.json","wifi.json","ab-x.raw.part","ab-/x.raw","ab-x%2f.raw","ab-x.raw?x",""})assert(!storage_public_name(s));
 StorageConfig cfg{};
 assert(storage_parse_config(R"({"ssid":"test","password":"password!","endpoint":"ws://192.168.1.2:8765/"})",cfg));
 assert(!strcmp(cfg.ssid,"test") && !strcmp(cfg.password,"password!"));
 for(auto* s:{"{}",R"({"ssid":"","password":"x"})",R"({"ssid":1,"password":"x"})",R"({"ssid":"x","password":null})",R"({"ssid":"x","password":"x","endpoint":"https://x"})",R"({"ssid":"x","password":"x","ssid":"y"})"})assert(!storage_parse_config(s,cfg));
 std::string big="{\"ssid\":\""+std::string(33,'x')+"\",\"password\":\"\"}";
 assert(!storage_parse_config(big.c_str(),cfg));
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
