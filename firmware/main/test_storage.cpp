#include "test_storage.h"
#include "storage_files.h"
#include "network.h"
#include "investigation.h"
#include "investigation_capture.h"
#include "diagnostic_events.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "mbedtls/sha256.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include <atomic>
#include <cstring>
#include <string>
#include <dirent.h>
#include <sys/stat.h>
#include <unistd.h>

namespace {
constexpr const char* root="/sdcard/tricorder";
constexpr const char* captures="/sdcard/tricorder/captures";
std::atomic<bool> ready{false};
SemaphoreHandle_t file_mutex;
void clear(void* data,size_t size) {
    auto* p=static_cast<volatile unsigned char*>(data);while(size--)*p++=0;
}
bool load_config(StorageConfig& config) {
    return storage_load_config(root,config);
}
bool apply_config(const StorageConfig& config) {
    if(config.endpoint[0])investigation_set_endpoint(config.endpoint);
    return network_connect_saved(config.ssid,config.password);
}
void provision(const char* json) {
    StorageConfig config{},existing{};bool ok=storage_parse_config(json,config);
    if(ok && ready.load()) {
        xSemaphoreTake(file_mutex,portMAX_DELAY);
        const bool same=load_config(existing) && !strcmp(config.ssid,existing.ssid) &&
            !strcmp(config.password,existing.password) && !strcmp(config.endpoint,existing.endpoint);
        ok=same || storage_replace_config(root,json);
        xSemaphoreGive(file_mutex);
    } else ok=false;
    if(ok)ok=apply_config(config);
    clear(&config,sizeof(config));clear(&existing,sizeof(existing));
    auto* event=diagnostic_event("storage_config");
    cJSON_AddStringToObject(event,"result",ok?"pass":"fail");
    cJSON_AddStringToObject(event,"source","usb");diagnostic_emit(event);
}
void console_task(void*) {
    char line[1025]{};size_t used=0;bool overflow=false;
    for(;;) {
        unsigned char ch;auto n=read(STDIN_FILENO,&ch,1);
        if(n<=0){clearerr(stdin);vTaskDelay(pdMS_TO_TICKS(10));continue;}
        if(ch=='\n') {
            constexpr const char* prefix="TRICORDER_CONFIG ";
            if(!overflow && !strncmp(line,prefix,strlen(prefix)))provision(line+strlen(prefix));
            constexpr const char* replay="TRICORDER_REPLAY ";
            if(!overflow && !strncmp(line,replay,strlen(replay))) {
                bool accepted=investigation_request_replay(line+strlen(replay));
                auto* e=diagnostic_event("replay_requested");cJSON_AddBoolToObject(e,"accepted",accepted);diagnostic_emit(e);
            }
            clear(line,sizeof(line));used=0;overflow=false;
        } else if(ch!='\r') {
            if(ch==0 || used==sizeof(line)-1)overflow=true;
            if(!overflow)line[used++]=ch;
        }
    }
}
esp_err_t list_files(httpd_req_t* request) {
    if(!ready.load())return httpd_resp_send_err(request,HTTPD_500_INTERNAL_SERVER_ERROR,"SD unavailable");
    auto* result=cJSON_CreateObject();auto* names=cJSON_AddArrayToObject(result,"files");
    xSemaphoreTake(file_mutex,portMAX_DELAY);
    DIR* dir=opendir(captures);unsigned count=0;bool truncated=false;
    if(dir) {
        while(auto* entry=readdir(dir))if(storage_public_name(entry->d_name)) {
            if(count++>=128){truncated=true;break;}
            cJSON_AddItemToArray(names,cJSON_CreateString(entry->d_name));
        }
        closedir(dir);
    }
    xSemaphoreGive(file_mutex);
    cJSON_AddBoolToObject(result,"truncated",truncated);
    char* json=cJSON_PrintUnformatted(result);httpd_resp_set_type(request,"application/json");
    auto rc=httpd_resp_send(request,json,HTTPD_RESP_USE_STRLEN);cJSON_free(json);cJSON_Delete(result);return rc;
}
esp_err_t get_file(httpd_req_t* request) {
    // Accept only public basenames, never paths or URL decoding.
    const char* name=request->uri+strlen("/test-file/");
    if(!ready.load() || !storage_public_name(name))return httpd_resp_send_err(request,HTTPD_404_NOT_FOUND,"No public capture");
    std::string path=std::string(captures)+"/"+name;
    xSemaphoreTake(file_mutex,portMAX_DELAY);FILE* file=fopen(path.c_str(),"rb");xSemaphoreGive(file_mutex);
    if(!file)return httpd_resp_send_err(request,HTTPD_404_NOT_FOUND,"No public capture");
    httpd_resp_set_type(request,strstr(name,".json")?"application/json":"application/octet-stream");
    auto* buffer=static_cast<char*>(heap_caps_malloc(16384,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
    if(!buffer){xSemaphoreTake(file_mutex,portMAX_DELAY);fclose(file);xSemaphoreGive(file_mutex);return ESP_ERR_NO_MEM;}
    esp_err_t result=ESP_OK;
    for(;;) {
        xSemaphoreTake(file_mutex,portMAX_DELAY);size_t n=fread(buffer,1,16384,file);
        bool failed=ferror(file);xSemaphoreGive(file_mutex);
        if(failed){result=ESP_FAIL;break;}
        if(!n)break;
        if((result=httpd_resp_send_chunk(request,buffer,n))!=ESP_OK)break;
    }
    xSemaphoreTake(file_mutex,portMAX_DELAY);fclose(file);xSemaphoreGive(file_mutex);
    free(buffer);
    if(result==ESP_OK)result=httpd_resp_send_chunk(request,nullptr,0);
    return result;
}
void resources(const char* id,const char* phase) {
    auto* event=diagnostic_event("storage_resources");
    cJSON_AddStringToObject(event,"capture_id",id);cJSON_AddStringToObject(event,"phase",phase);
    cJSON_AddNumberToObject(event,"free_dma",heap_caps_get_free_size(MALLOC_CAP_DMA));
    cJSON_AddNumberToObject(event,"largest_dma",heap_caps_get_largest_free_block(MALLOC_CAP_DMA));
    cJSON_AddNumberToObject(event,"minimum_free_dma_since_boot",heap_caps_get_minimum_free_size(MALLOC_CAP_DMA));
    cJSON_AddNumberToObject(event,"free_internal",heap_caps_get_free_size(MALLOC_CAP_INTERNAL));
    diagnostic_emit(event);
}
}
bool test_storage_load_capture(const char* id,InvestigationCapture& output) {
    if(!ready.load() || !id || !storage_public_name((std::string(id)+".raw").c_str()))return false;
    xSemaphoreTake(file_mutex,portMAX_DELAY);
    bool ok=investigation_load_capture((std::string(captures)+"/"+id).c_str(),id,output);
    xSemaphoreGive(file_mutex);return ok;
}
bool test_storage_archive(const unsigned char* bytes,size_t size,const cJSON* metadata) {
    if(!ready.load())return false;
    auto* id=cJSON_GetObjectItemCaseSensitive(metadata,"capture_id");
    auto* expected=cJSON_GetObjectItemCaseSensitive(metadata,"sha256");
    if(!cJSON_IsString(id) || !cJSON_IsString(expected))return false;
    std::string basename=std::string(id->valuestring)+".raw";
    if(!storage_public_name(basename.c_str()))return false;
    unsigned char hash[32];char hex[65]{};
    if(mbedtls_sha256(bytes,size,hash,0))return false;
    for(unsigned i=0;i<32;++i)snprintf(hex+i*2,3,"%02x",hash[i]);
    if(strcmp(hex,expected->valuestring))return false;
    resources(id->valuestring,"before_archive");
    char* json=nullptr;
    int64_t start=esp_timer_get_time();xSemaphoreTake(file_mutex,portMAX_DELAY);
    std::string base=std::string(captures)+"/"+id->valuestring;
    bool ok=storage_write_verified((base+".raw").c_str(),bytes,size);
    // Metadata is the commit record; orphan raw/.part files are incomplete.
    if(ok) {
        // Do not hold serialized metadata while the raw-file I/O needs memory.
        json=cJSON_PrintUnformatted(metadata);
        ok=json && storage_write_verified((base+".json").c_str(),reinterpret_cast<unsigned char*>(json),strlen(json));
    }
    xSemaphoreGive(file_mutex);cJSON_free(json);
    auto* event=diagnostic_event("storage_archive");cJSON_AddStringToObject(event,"capture_id",id->valuestring);
    cJSON_AddStringToObject(event,"result",ok?"pass":"fail");cJSON_AddStringToObject(event,"sha256",hex);
    cJSON_AddNumberToObject(event,"size_bytes",size);cJSON_AddNumberToObject(event,"write_verify_us",esp_timer_get_time()-start);
    diagnostic_emit(event);resources(id->valuestring,"after_archive");return ok;
}
void test_storage_init(const char* boot,bool mounted,bool connect_saved) {
    file_mutex=xSemaphoreCreateMutex();configASSERT(file_mutex);
    struct stat info{};
    auto directory=[&](const char* path){return mkdir(path,0700)==0 || (stat(path,&info)==0 && S_ISDIR(info.st_mode));};
    ready.store(mounted && directory(root) && directory(captures));
    auto* event=diagnostic_event("storage_ready");cJSON_AddBoolToObject(event,"mounted",ready.load());diagnostic_emit(event);
    if(ready.load()) {
        // Exercise a full A/B-sized file without starting sensors.
        constexpr size_t size=1152000;
        auto* data=static_cast<unsigned char*>(heap_caps_malloc(size,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
        bool ok=false;
        if(data) {
            for(size_t i=0;i<size;++i)data[i]=(i*37+11)&255;
            unsigned char hash[32];char hex[65]{},id[64];
            mbedtls_sha256(data,size,hash,0);
            for(unsigned i=0;i<32;++i)snprintf(hex+i*2,3,"%02x",hash[i]);
            snprintf(id,sizeof(id),"ab-storage-%s",boot);
            auto* metadata=cJSON_CreateObject();cJSON_AddStringToObject(metadata,"capture_id",id);
            cJSON_AddStringToObject(metadata,"format","synthetic_storage_test");cJSON_AddStringToObject(metadata,"boot_id",boot);
            cJSON_AddStringToObject(metadata,"sha256",hex);cJSON_AddNumberToObject(metadata,"size_bytes",size);
            ok=test_storage_archive(data,size,metadata);cJSON_Delete(metadata);free(data);
        }
        auto* check=diagnostic_event("storage_selftest");cJSON_AddStringToObject(check,"result",ok?"pass":"fail");diagnostic_emit(check);
        StorageConfig config{};
        if(connect_saved && load_config(config)) {
            bool applied=apply_config(config);auto* e=diagnostic_event("storage_config");
            cJSON_AddStringToObject(e,"source","sd_boot");cJSON_AddStringToObject(e,"result",applied?"pass":"fail");diagnostic_emit(e);
        }
        clear(&config,sizeof(config));
    }
    configASSERT(xTaskCreate(console_task,"usb_config",6144,nullptr,3,nullptr)==pdPASS);
}
void test_storage_http(httpd_handle_t server) {
    httpd_uri_t route{};route.method=HTTP_GET;route.uri="/test-files";route.handler=list_files;
    auto a=httpd_register_uri_handler(server,&route);
    route.uri="/test-file/*";route.handler=get_file;auto b=httpd_register_uri_handler(server,&route);
    diagnostic_check("storage_http",a==ESP_OK && b==ESP_OK?"pass":"fail","Public capture files only; credentials excluded.");
}
