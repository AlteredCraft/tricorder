#include "investigation_capture.h"
#include "level_median.h"
#include "esp_heap_caps.h"
#include "mbedtls/sha256.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <cmath>
#include <algorithm>

bool investigation_load_capture(const char* base,const char* id,InvestigationCapture& out) {
    if(out.bytes || out.metadata || out.measurement)return false;
    constexpr size_t size=1152000;
    auto* json=static_cast<char*>(heap_caps_malloc(32769,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
    if(!json)return false;
    FILE* file=fopen((std::string(base)+".json").c_str(),"rb");
    if(!file){free(json);return false;}
    size_t n=fread(json,1,32769,file);bool ok=!ferror(file) && n>0 && n<32769;fclose(file);
    if(ok){json[n]=0;out.metadata=cJSON_ParseWithOpts(json,nullptr,true);}free(json);
    auto* m=out.metadata;
    auto equal=[&](const char* key,const char* value){auto* v=cJSON_GetObjectItemCaseSensitive(m,key);return cJSON_IsString(v) && !strcmp(v->valuestring,value);};
    auto number=[&](const char* key,double value){auto* v=cJSON_GetObjectItemCaseSensitive(m,key);return cJSON_IsNumber(v) && v->valuedouble==value;};
    auto* expected=cJSON_GetObjectItemCaseSensitive(m,"sha256");
    if(!ok || !equal("capture_id",id) || !equal("format","pcm_s16le") ||
       !number("size_bytes",size) || !number("frames",144000) || !number("channels",4) ||
       !number("sample_rate_hz",48000) || !number("source_slot",0) || !cJSON_IsString(expected))return false;
    out.bytes=static_cast<unsigned char*>(heap_caps_malloc(size,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
    if(!out.bytes)return false;
    file=fopen((std::string(base)+".raw").c_str(),"rb");if(!file)return false;
    n=fread(out.bytes,1,size,file);ok=n==size && fgetc(file)==EOF && !ferror(file);fclose(file);
    if(!ok)return false;
    unsigned char digest[32];char hex[65]{};
    if(mbedtls_sha256(out.bytes,size,digest,0))return false;
    for(unsigned i=0;i<32;++i)snprintf(hex+i*2,3,"%02x",digest[i]);
    if(strcmp(hex,expected->valuestring))return false;
    uint64_t squared=0;unsigned peak=0,clipped=0;
    for(size_t i=0;i<size;i+=8) {
        int16_t sample;memcpy(&sample,out.bytes+i,2);int v=sample;
        squared+=static_cast<int64_t>(v)*v;peak=std::max(peak,static_cast<unsigned>(std::abs(v)));
        clipped+=v==-32768 || v==32767;
    }
    double rms=sqrt(static_cast<double>(squared)/144000);
    out.measurement=cJSON_CreateObject();if(!out.measurement)return false;
    cJSON_AddNumberToObject(out.measurement,"frames",144000);cJSON_AddNumberToObject(out.measurement,"rms_counts",rms);
    cJSON_AddNumberToObject(out.measurement,"peak_counts",peak);cJSON_AddNumberToObject(out.measurement,"clipped_samples",clipped);
    if(rms)cJSON_AddNumberToObject(out.measurement,"rms_dbfs",20*log10(rms/32768));else cJSON_AddNullToObject(out.measurement,"rms_dbfs");
    const double median=median_window_dbfs(reinterpret_cast<const int16_t*>(out.bytes),144000,4,0);
    if(std::isfinite(median))cJSON_AddNumberToObject(out.measurement,"median_dbfs",median);else cJSON_AddNullToObject(out.measurement,"median_dbfs");
    out.size=size;return true;
}
