#include "storage_files.h"
#include "investigation_wire.h"
#include "cJSON.h"
#include <cstring>
#include <string>
#include <cstdlib>
#include <fcntl.h>
#include <unistd.h>
#ifdef ESP_PLATFORM
#include "esp_heap_caps.h"
#endif

bool storage_parse_config(const char* json, StorageConfig& out) {
    out={};
    if(!json || strlen(json)>1000 || strstr(json,"\\u0000"))return false;
    auto* root=cJSON_ParseWithOpts(json,nullptr,true);
    if(!cJSON_IsObject(root)){cJSON_Delete(root);return false;}
    bool ok=true;unsigned ssids=0,passwords=0,endpoints=0;
    for(auto* item=root->child;item;item=item->next) {
        char* dest=nullptr;size_t capacity=0;
        if(!strcmp(item->string,"ssid")){dest=out.ssid;capacity=sizeof(out.ssid);++ssids;}
        else if(!strcmp(item->string,"password")){dest=out.password;capacity=sizeof(out.password);++passwords;}
        else if(!strcmp(item->string,"endpoint")){dest=out.endpoint;capacity=sizeof(out.endpoint);++endpoints;}
        else {ok=false;break;}
        if(!cJSON_IsString(item) || strlen(item->valuestring)>=capacity){ok=false;break;}
        strcpy(dest,item->valuestring);
    }
    InvestigationEndpoint endpoint;
    ok=ok && ssids==1 && passwords==1 && endpoints<=1 && out.ssid[0] &&
        (!out.endpoint[0] || endpoint.parse(out.endpoint));
    cJSON_Delete(root);
    if(!ok)out={};
    return ok;
}

bool storage_public_name(const char* name) {
    if(!name || strncmp(name,"ab-",3) || strlen(name)>90)return false;
    for(const char* p=name;*p;++p)
        if(!((*p>='a' && *p<='z') || (*p>='0' && *p<='9') || *p=='-' || *p=='.'))return false;
    const char* dot=strchr(name,'.');
    return dot && (!strcmp(dot,".raw") || !strcmp(dot,".json"));
}

// Writes and reads go through one aligned, DMA-capable 16 KiB stage. From an
// unaligned PSRAM source the SDMMC driver writes one 512-byte sector per command
// (about 2.3 s per 1.15 MB capture, during which the LVGL probe stalled for as long;
// G-0001.02 C2); an aligned stage lets FatFs pass whole sectors in one transfer.
bool storage_write_verified(const char* path,const unsigned char* data,size_t size) {
    if(!data || !size || access(path,F_OK)==0)return false;
    constexpr size_t chunk=16384;
#ifdef ESP_PLATFORM
    auto* stage=static_cast<unsigned char*>(heap_caps_aligned_alloc(128,chunk,MALLOC_CAP_DMA|MALLOC_CAP_INTERNAL));
#else
    auto* stage=static_cast<unsigned char*>(malloc(chunk));
#endif
    if(!stage)return false;
    const std::string partial=std::string(path)+".part";
    int fd=open(partial.c_str(),O_WRONLY|O_CREAT|O_EXCL,0600);
    if(fd<0){free(stage);return false;}
    bool ok=true;size_t offset=0;
    while(ok && offset<size) {
        const size_t count=size-offset<chunk?size-offset:chunk;
        memcpy(stage,data+offset,count);
        size_t done=0;
        while(done<count) {
            auto n=write(fd,stage+done,count-done);
            if(n<=0){ok=false;break;}done+=n;
        }
        offset+=done;
    }
    ok=fsync(fd)==0 && ok;ok=close(fd)==0 && ok;
    if(!ok){free(stage);return false;}
    fd=open(partial.c_str(),O_RDONLY);if(fd<0){free(stage);return false;}
    offset=0;
    while(offset<size) {
        const size_t count=size-offset<chunk?size-offset:chunk;
        auto n=read(fd,stage,count);
        if(n<=0 || memcmp(stage,data+offset,n)){ok=false;break;}offset+=n;
    }
    if(ok)ok=read(fd,stage,1)==0;
    ok=close(fd)==0 && ok;
    free(stage);
    return ok && access(path,F_OK)!=0 && rename(partial.c_str(),path)==0;
}

namespace {
bool read_config_file(const std::string& path,StorageConfig& config) {
    char json[1001]{};FILE* file=fopen(path.c_str(),"rb");if(!file)return false;
    size_t count=fread(json,1,sizeof(json),file);bool ok=!ferror(file) && count<sizeof(json);
    fclose(file);ok=ok && storage_parse_config(json,config);
    auto* p=static_cast<volatile char*>(json);for(size_t i=0;i<sizeof(json);++i)p[i]=0;
    return ok;
}
}
bool storage_load_config(const char* directory,StorageConfig& out) {
    return read_config_file(std::string(directory)+"/wifi.json",out) ||
        read_config_file(std::string(directory)+"/wifi.previous.json",out);
}
bool storage_replace_config(const char* directory,const char* json) {
    StorageConfig config{};bool valid=storage_parse_config(json,config);
    auto* p=reinterpret_cast<volatile unsigned char*>(&config);for(size_t i=0;i<sizeof(config);++i)p[i]=0;
    if(!valid)return false;
    const std::string current=std::string(directory)+"/wifi.json",previous=std::string(directory)+"/wifi.previous.json",
        next=std::string(directory)+"/wifi.next.json";
    // Only private configuration staging files may be replaced. Captures never are.
    if(access(next.c_str(),F_OK)==0 && unlink(next.c_str()))return false;
    if(access((next+".part").c_str(),F_OK)==0 && unlink((next+".part").c_str()))return false;
    if(!storage_write_verified(next.c_str(),reinterpret_cast<const unsigned char*>(json),strlen(json)))return false;
    if(access(current.c_str(),F_OK)==0) {
        StorageConfig old{};const bool current_valid=read_config_file(current,old);
        auto* q=reinterpret_cast<volatile unsigned char*>(&old);for(size_t i=0;i<sizeof(old);++i)q[i]=0;
        if(current_valid) {
            if(access(previous.c_str(),F_OK)==0 && unlink(previous.c_str()))return false;
            if(rename(current.c_str(),previous.c_str()))return false;
        } else if(unlink(current.c_str()))return false;
    }
    return rename(next.c_str(),current.c_str())==0;
}
