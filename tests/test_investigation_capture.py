"""Exercise the actual bounded capture owner with injected codec failures."""
from pathlib import Path
import subprocess
import tempfile
import unittest

def write_stubs(p):
    """ESP-IDF stand-ins for host builds of the capture owner."""
    (p/'mbedtls').mkdir()
    (p/'esp_codec_dev.h').write_text('''#pragma once
using esp_codec_dev_handle_t=void*;
constexpr int ESP_OK=0;
struct esp_codec_dev_sample_info_t {int sample_rate=0,channel=0,bits_per_sample=0;};
int esp_codec_dev_open(void*,const esp_codec_dev_sample_info_t*);
int esp_codec_dev_close(void*);
int esp_codec_dev_set_out_mute(void*,bool);
int esp_codec_dev_set_in_gain(void*,float);
int esp_codec_dev_read(void*,void*,int);
''')
    (p/'esp_heap_caps.h').write_text('''#pragma once
#include <cstdlib>
constexpr int MALLOC_CAP_SPIRAM=1,MALLOC_CAP_8BIT=2;
inline void* heap_caps_malloc(size_t n,int){return malloc(n);}
inline void* heap_caps_calloc(size_t n,size_t s,int){return calloc(n,s);}
inline void* heap_caps_aligned_alloc(size_t a,size_t n,int){return aligned_alloc(a,(n+a-1)/a*a);}
''')
    (p/'esp_timer.h').write_text('#pragma once\n#include <cstdint>\nint64_t esp_timer_get_time();\n')
    (p/'mbedtls/sha256.h').write_text('''#pragma once
#include <cstddef>
// Deterministic hash stand-in; this test verifies ownership/extent, not SHA.
inline int mbedtls_sha256(const unsigned char* p,size_t n,unsigned char* out,int) {
 unsigned v=0;for(size_t i=0;i<n;++i)v=v*33+p[i];
 for(unsigned i=0;i<32;++i)out[i]=(v>>(i%4)*8);return 0;
}
''')


class InvestigationCaptureTests(unittest.TestCase):
    def test_acquisition_cleanup_integrity_cancel_and_capacity(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)
            write_stubs(p)
            (p/'driver.cpp').write_text(r'''
#include "investigation_capture.h"
#include "audio_devices.h"
#include "audio_ingress.h"
#include "diagnostic_events.h"
#include "spectrum_display.h"
#include <cassert>
#include <cmath>
#include <cstring>
#include <cstdio>
#include <string>
static int opens=0,closes=0,reads=0,mode=0;
static AudioIngressSnapshot counters;
static std::atomic<bool> cancel_flag{false};
void* diagnostic_microphone(){return (void*)1;}
void* diagnostic_speaker(){return (void*)2;}
int esp_codec_dev_open(void*,const esp_codec_dev_sample_info_t*){++opens;return 0;}
int esp_codec_dev_close(void*){++closes;return 0;}
int esp_codec_dev_set_out_mute(void*,bool muted){assert(muted);return mode==1?-1:0;}
int esp_codec_dev_set_in_gain(void*,float gain){assert(gain==24);return 0;}
int esp_codec_dev_read(void*,void* target,int size){
 ++reads;if(mode==2)return -1;
 auto* pcm=(int16_t*)target;
 for(int i=0;i<size/2;++i)pcm[i]=i%4==0?1000:0;
 counters.read_bytes+=size;counters.dma_bytes+=size;
 if(mode==3)++counters.overflows;
 if(mode==4)cancel_flag=true;
 return 0;
}
static int taps=0,events=0;
cJSON* diagnostic_event(const char* name){
 assert(!strcmp(name,"investigation_live_spectrum"));++events;return cJSON_CreateObject();
}
void diagnostic_emit(cJSON* e){
 assert(cJSON_GetObjectItem(e,"views")->valuedouble==taps);cJSON_Delete(e);
}
void tap(const float* db){
 ++taps;for(size_t i=0;i<spectrum_band_count;++i)assert(db[i]>=spectrum_floor_db && db[i]<0);
}
AudioIngressSnapshot audio_ingress_snapshot(){return counters;}
bool begin_audio_epoch(AudioIngressSnapshot& before){before=counters;return true;}
int64_t esp_timer_get_time(){static int64_t t=0;return ++t;}
int main(int argc,char** argv){
 assert(argc==2);
 for(mode=0;mode<5;++mode){
  opens=closes=reads=0;cancel_flag=false;
  InvestigationCapture capture;
  bool ok=investigation_capture("boot","session","take",cancel_flag,capture);
  assert(opens==2 && closes==2 && !events);
  if(!mode){
   assert(ok && capture.size==1152000 && reads==165);
   assert(cJSON_GetObjectItem(capture.metadata,"warmup_frames")->valuedouble==24000);
   assert(cJSON_GetObjectItem(capture.metadata,"epoch_start_us")->valuedouble <
          cJSON_GetObjectItem(capture.metadata,"acquisition_start_us")->valuedouble);
   assert(cJSON_GetObjectItem(cJSON_GetObjectItem(capture.metadata,"ingress_after"),"read_bytes")->valuedouble-
          cJSON_GetObjectItem(cJSON_GetObjectItem(capture.metadata,"ingress_before"),"read_bytes")->valuedouble==1344000);
   assert(cJSON_GetArraySize(cJSON_GetObjectItem(capture.metadata,"ingress_blocks"))==141);
   assert(cJSON_GetObjectItem(capture.measurement,"rms_counts")->valuedouble==1000);
   assert(cJSON_GetObjectItem(capture.measurement,"frames")->valuedouble==144000);
   assert(fabs(cJSON_GetObjectItem(capture.measurement,"median_dbfs")->valuedouble-20*log10(1000.0/32768))<1e-9);
   // The display tap sees every 4th retained block and changes no evidence.
   { InvestigationCapture viewed;opens=closes=0;
     assert(investigation_capture("boot","session","take",cancel_flag,viewed,tap));
     assert(taps==35 && events==1 && viewed.size==capture.size && !memcmp(viewed.bytes,capture.bytes,viewed.size));
     events=0; }
   auto* wire=cJSON_PrintUnformatted(capture.metadata);assert(strlen(wire)<32000);cJSON_free(wire);
   std::string base=std::string(argv[1])+"/saved";
   FILE* file=fopen((base+".raw").c_str(),"wb");assert(file);assert(fwrite(capture.bytes,1,capture.size,file)==capture.size);fclose(file);
   wire=cJSON_PrintUnformatted(capture.metadata);
   file=fopen((base+".json").c_str(),"wb");assert(file);fputs(wire,file);fclose(file);cJSON_free(wire);
   { InvestigationCapture replay;assert(investigation_load_capture(base.c_str(),"take",replay));
     assert(replay.size==capture.size && !memcmp(replay.bytes,capture.bytes,replay.size));
     assert(cJSON_GetObjectItem(replay.measurement,"rms_counts")->valuedouble==1000);
     assert(fabs(cJSON_GetObjectItem(replay.measurement,"median_dbfs")->valuedouble-20*log10(1000.0/32768))<1e-9);
     assert(!investigation_load_capture(base.c_str(),"take",replay)); }
   { InvestigationCapture wrong;assert(!investigation_load_capture(base.c_str(),"other",wrong)); }
   file=fopen((base+".raw").c_str(),"r+b");fputc(capture.bytes[0]^1,file);fclose(file);
   { InvestigationCapture corrupt;assert(!investigation_load_capture(base.c_str(),"take",corrupt)); }
   file=fopen((base+".raw").c_str(),"r+b");fputc(capture.bytes[0],file);fclose(file);
   file=fopen((base+".raw").c_str(),"ab");fputc(1,file);fclose(file);
   { InvestigationCapture extra;assert(!investigation_load_capture(base.c_str(),"take",extra)); }
   file=fopen((base+".raw").c_str(),"wb");fputc(1,file);fclose(file);
   { InvestigationCapture short_file;assert(!investigation_load_capture(base.c_str(),"take",short_file)); }
   // Reusing a live output would overwrite its owned allocation: rejected.
   assert(!investigation_capture("boot","session","take",cancel_flag,capture));
  } else assert(!ok);
  if(mode==1)assert(reads==0);
  if(mode==4)assert(reads==1);
 }
}
''')
            cjson=Path('.tools/esp-idf/components/json/cJSON')
            r=subprocess.run(['clang','-fsanitize=address','-c',str(cjson/'cJSON.c'),'-o',str(p/'json.o')],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            r=subprocess.run(['clang++','-std=c++17','-Wall','-Wextra','-Werror','-fsanitize=address',
                              '-I',str(p),'-I','firmware/main','-I',str(cjson),str(p/'driver.cpp'),
                              'firmware/main/investigation_capture.cpp','firmware/main/investigation_replay.cpp','firmware/main/speech_filter.cpp',
                              'firmware/main/spectrum.cpp','firmware/main/spectrum_display.cpp',str(p/'json.o'),'-o',str(p/'test')],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            r=subprocess.run([str(p/'test'),str(p)],capture_output=True,text=True,timeout=15)
            self.assertEqual(r.returncode,0,r.stderr)


class QuestionRecordingTests(unittest.TestCase):
    """The spoken question: slot 0 filtered to 16 kHz mono, own buffer, tap to stop, 8 s limit."""
    def test_limit_operator_stop_cancel_and_driver_loss(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)
            write_stubs(p)
            (p/'driver.cpp').write_text(r'''
#include "investigation_capture.h"
#include "audio_devices.h"
#include "audio_ingress.h"
#include "diagnostic_events.h"
#include <cassert>
#include <cmath>
#include <cstring>
#include <initializer_list>
static int opens=0,closes=0,reads=0,mode=0,stop_at=0;
static long phase=0;
static AudioIngressSnapshot counters;
static std::atomic<bool> cancel_flag{false},stop_flag{false};
void* diagnostic_microphone(){return (void*)1;}
void* diagnostic_speaker(){return (void*)2;}
int esp_codec_dev_open(void*,const esp_codec_dev_sample_info_t* info){++opens;assert(info->sample_rate==48000);return 0;}
int esp_codec_dev_close(void*){++closes;return 0;}
int esp_codec_dev_set_out_mute(void*,bool muted){assert(muted);return mode==1?-1:0;}
int esp_codec_dev_set_in_gain(void*,float gain){assert(gain==24);return 0;}
int esp_codec_dev_read(void*,void* target,int size){
 ++reads;if(mode==2 && reads==20)return -1;
 auto* pcm=(int16_t*)target;
 // Slot 0: 1 kHz at amplitude 1000 (-33.3 dBFS RMS), clipped once per block in mode 5.
 for(int i=0;i<size/8;++i,++phase){
  pcm[i*4]=(int16_t)lround(1000*sin(2*M_PI*1000*phase/48000.0));pcm[i*4+1]=pcm[i*4+2]=pcm[i*4+3]=7;
  if(mode==5 && i==0)pcm[0]=32767;
 }
 counters.read_bytes+=size;counters.dma_bytes+=size;
 if(mode==3 && reads==20)++counters.overflows;
 if(mode==4 && reads==20)cancel_flag=true;
 if(stop_at && reads==stop_at)stop_flag=true;
 return 0;
}
cJSON* diagnostic_event(const char*){assert(false);return nullptr;}
void diagnostic_emit(cJSON*){assert(false);}
static int taps=0;static float last_level=-200;
void tap(float dbfs){++taps;last_level=dbfs;}
AudioIngressSnapshot audio_ingress_snapshot(){return counters;}
bool begin_audio_epoch(AudioIngressSnapshot& before){before=counters;return true;}
int64_t esp_timer_get_time(){static int64_t t=0;return ++t;}
double number(const cJSON* o,const char* k){return cJSON_GetObjectItem(o,k)->valuedouble;}
const char* text(const cJSON* o,const char* k){return cJSON_GetObjectItem(o,k)->valuestring;}
int main(){
 // 8 s limit: 12 settling reads, then 375 blocks of 1024 frames -> 128000 frames at 16 kHz.
 { InvestigationCapture q;
   assert(investigation_record_question("boot","session","session-q1",cancel_flag,stop_flag,q,tap));
   assert(opens==2 && closes==2 && reads==12+375 && taps==375);
   assert(q.size==256000 && !q.measurement);
   assert(number(q.metadata,"frames")==128000 && number(q.metadata,"size_bytes")==256000);
   assert(number(q.metadata,"sample_rate_hz")==16000 && number(q.metadata,"channels")==1);
   assert(number(q.metadata,"source_rate_hz")==48000 && number(q.metadata,"source_slot")==0);
   assert(number(q.metadata,"warmup_frames")==12000 && number(q.metadata,"input_clipped")==0);
   assert(!strcmp(text(q.metadata,"stopped_by"),"limit") && !strcmp(text(q.metadata,"question_id"),"session-q1"));
   assert(!strcmp(text(q.metadata,"filter"),"hpf80-lpf6500-63tap-decimate3"));
   assert(!strcmp(text(q.metadata,"format"),"pcm_s16le") && strlen(text(q.metadata,"sha256"))==64);
   assert(cJSON_IsTrue(cJSON_GetObjectItem(q.metadata,"driver_epoch_integrity")));
   assert(number(q.metadata,"acquisition_end_us")>number(q.metadata,"acquisition_start_us"));
   assert(cJSON_GetArraySize(q.metadata)==19);
   assert(last_level>-34.0f && last_level<-32.5f);
   // Output is the filtered measurement slot, not a copy of the raw frames.
   double energy=0;auto* s=(const int16_t*)q.bytes;for(int i=8000;i<128000;++i)energy+=double(s[i])*s[i];
   assert(fabs(sqrt(energy/120000)-707.1)<25);
   assert(!investigation_record_question("boot","session","session-q1",cancel_flag,stop_flag,q,tap)); }
 // Operator stop after 18 recorded blocks; a stop during settling still keeps one block.
 for(int at:{30,5}) { opens=closes=reads=0;stop_flag=false;stop_at=at;InvestigationCapture q;
   assert(investigation_record_question("boot","session","session-q2",cancel_flag,stop_flag,q));
   const int blocks=at>12?at-12:1;
   assert(reads==12+blocks && closes==2 && number(q.metadata,"frames")==blocks*1024/3);
   assert(!strcmp(text(q.metadata,"stopped_by"),"operator")); }
 stop_at=0;stop_flag=false;
 for(mode=1;mode<6;++mode) { opens=closes=reads=0;cancel_flag=false;InvestigationCapture q;
   bool ok=investigation_record_question("boot","session","session-q3",cancel_flag,stop_flag,q);
   assert(opens==2 && closes==2);
   if(mode==1)assert(!ok && reads==0);
   if(mode>=2 && mode<=4)assert(!ok);
   if(mode==5)assert(ok && number(q.metadata,"input_clipped")==375); }
}
''')
            cjson=Path('.tools/esp-idf/components/json/cJSON')
            r=subprocess.run(['clang','-fsanitize=address','-c',str(cjson/'cJSON.c'),'-o',str(p/'json.o')],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            r=subprocess.run(['clang++','-std=c++17','-Wall','-Wextra','-Werror','-fsanitize=address',
                              '-I',str(p),'-I','firmware/main','-I',str(cjson),str(p/'driver.cpp'),
                              'firmware/main/investigation_capture.cpp','firmware/main/speech_filter.cpp',
                              'firmware/main/spectrum.cpp','firmware/main/spectrum_display.cpp',str(p/'json.o'),'-o',str(p/'test')],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            r=subprocess.run([str(p/'test')],capture_output=True,text=True,timeout=15)
            self.assertEqual(r.returncode,0,r.stderr)
