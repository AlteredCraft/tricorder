#include "test_storage.h"
#include "storage_files.h"
#include "network.h"
#include "setup.h"
#include "diagnostic_events.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include <atomic>
#include <cstring>
#include <sys/stat.h>
#include <unistd.h>

namespace {
constexpr const char* root="/sdcard/tricorder";
std::atomic<bool> ready{false};
SemaphoreHandle_t file_mutex;
void clear(void* data,size_t size) {
    auto* p=static_cast<volatile unsigned char*>(data);while(size--)*p++=0;
}
bool load_config(StorageConfig& config) {
    return storage_load_config(root,config);
}
bool apply_config(const StorageConfig& config) {
    network_set_known(config.known,config.known_count);
    // Hotspot mode: the Mac joins the device, and the endpoint follows its lease (network.cpp).
    if(config.access_point)return network_start_access_point(config.ssid,config.password);
    if(config.endpoint[0])setup_set_endpoint(config.endpoint,EndpointSource::Sd);
    return network_connect_saved(config.ssid,config.password);
}
void provision(const char* json) {
    StorageConfig config{},existing{};bool ok=storage_parse_config(json,config);
    if(ok && ready.load()) {
        xSemaphoreTake(file_mutex,portMAX_DELAY);
        const bool same=load_config(existing) && storage_config_equal(config,existing);
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
            if(!overflow && !strcmp(line,"TRICORDER_POWER_STEPS")) {
                auto* e=diagnostic_event("power_steps_requested");
                cJSON_AddBoolToObject(e,"accepted",diagnostic_request_power_steps());diagnostic_emit(e);
            }
            clear(line,sizeof(line));used=0;overflow=false;
        } else if(ch!='\r') {
            if(ch==0 || used==sizeof(line)-1)overflow=true;
            if(!overflow)line[used++]=ch;
        }
    }
}
}
void test_storage_init(bool mounted,bool connect_saved) {
    file_mutex=xSemaphoreCreateMutex();configASSERT(file_mutex);
    struct stat info{};
    ready.store(mounted && (mkdir(root,0700)==0 || (stat(root,&info)==0 && S_ISDIR(info.st_mode))));
    auto* event=diagnostic_event("storage_ready");cJSON_AddBoolToObject(event,"mounted",ready.load());diagnostic_emit(event);
    if(ready.load()) {
        StorageConfig config{};
        if(connect_saved && load_config(config)) {
            bool applied=apply_config(config);auto* e=diagnostic_event("storage_config");
            cJSON_AddStringToObject(e,"source","sd_boot");cJSON_AddStringToObject(e,"result",applied?"pass":"fail");diagnostic_emit(e);
        }
        clear(&config,sizeof(config));
    }
    configASSERT(xTaskCreate(console_task,"usb_config",12288,nullptr,3,nullptr)==pdPASS);
    // tools/capture_serial.py --console-command waits for this before it writes its line.
    diagnostic_emit(diagnostic_event("console_ready"));
}
