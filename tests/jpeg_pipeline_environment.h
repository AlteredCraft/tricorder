#pragma once
// Host fault-injection environment for the real jpeg_pipeline.cpp. This models
// RTOS ownership/wakeup, not the hardware codec (covered by device evidence).
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <mutex>
#include <set>
#include <string>
#include <thread>
#include <vector>

inline unsigned allocation_step=0,fail_step=0,live_semaphores=0,live_engines=0;
inline std::atomic<bool> codec_live{false},hold_codec{false};
inline std::set<void*> allocations;
inline bool fail_allocation() {return ++allocation_step==fail_step;}
inline void* allocate(size_t bytes,bool zero=false) {
    if (fail_allocation()) return nullptr;
    void* p=zero ? std::calloc(1,bytes):std::malloc(bytes);
    assert(p);allocations.insert(p);return p;
}
inline void host_free(void* p) {
    if (!p) return;
    assert(!codec_live.load());
    assert(allocations.erase(p)==1);std::free(p);
}
constexpr int MALLOC_CAP_SPIRAM=1;
inline void* heap_caps_malloc(size_t bytes,int) {return allocate(bytes);}
inline void* heap_caps_calloc(size_t n,size_t bytes,int) {return allocate(n*bytes,true);}
inline int64_t esp_timer_get_time() {
    return std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();
}

struct FakeSemaphore {std::mutex mutex;std::condition_variable changed;bool given=false;};
struct FakeTask {std::mutex mutex;std::condition_variable changed;unsigned notifications=0;std::thread thread;};
using SemaphoreHandle_t=FakeSemaphore*;using TaskHandle_t=FakeTask*;
inline thread_local FakeTask* running_task=nullptr;
inline std::vector<std::unique_ptr<FakeTask>> workers;
constexpr unsigned portMAX_DELAY=0xffffffff;constexpr int pdTRUE=1,pdPASS=1;
#define pdMS_TO_TICKS(n) (n)
#define configASSERT(n) assert(n)
inline SemaphoreHandle_t xSemaphoreCreateBinary() {
    if (fail_allocation()) return nullptr;
    ++live_semaphores;return new FakeSemaphore;
}
inline int xSemaphoreTake(SemaphoreHandle_t sem,unsigned timeout) {
    std::unique_lock<std::mutex> lock(sem->mutex);
    if (!sem->changed.wait_for(lock,std::chrono::milliseconds(timeout),[&]{return sem->given;})) return 0;
    sem->given=false;return pdTRUE;
}
inline void xSemaphoreGive(SemaphoreHandle_t sem) {
    std::lock_guard<std::mutex> lock(sem->mutex);sem->given=true;sem->changed.notify_one();
}
inline void vSemaphoreDelete(SemaphoreHandle_t sem) {--live_semaphores;delete sem;}
struct TaskExit {};
inline void vTaskDelete(TaskHandle_t) {throw TaskExit{};}
inline int xTaskCreate(void(*function)(void*),const char*,unsigned,void* context,unsigned,TaskHandle_t* output) {
    if (fail_allocation()) return 0;
    auto task=std::make_unique<FakeTask>();auto* ptr=task.get();*output=ptr;
    ptr->thread=std::thread([=]{running_task=ptr;try {function(context);} catch(const TaskExit&) {}});
    workers.push_back(std::move(task));return pdPASS;
}
inline void xTaskNotifyGive(TaskHandle_t task) {
    std::lock_guard<std::mutex> lock(task->mutex);++task->notifications;task->changed.notify_one();
}
inline unsigned ulTaskNotifyTake(int,unsigned) {
    auto* task=running_task;assert(task);
    std::unique_lock<std::mutex> lock(task->mutex);
    task->changed.wait(lock,[&]{return task->notifications!=0;});
    auto n=task->notifications;task->notifications=0;return n;
}
inline void vTaskDelay(unsigned ms) {std::this_thread::sleep_for(std::chrono::milliseconds(ms));}
inline void join_workers() {for (auto& w:workers) w->thread.join();workers.clear();}

using esp_err_t=int;using jpeg_encoder_handle_t=void*;
constexpr int ESP_OK=0,ESP_FAIL=-1,ESP_ERR_INVALID_SIZE=1,ESP_ERR_NO_MEM=2;
constexpr unsigned JPEG_ENC_ALLOC_OUTPUT_BUFFER=1,JPEG_ENCODE_IN_FORMAT_RGB565=2,JPEG_DOWN_SAMPLING_YUV420=3;
struct jpeg_encode_memory_alloc_cfg_t {unsigned buffer_direction;};
struct jpeg_encode_engine_cfg_t {int timeout_ms;};
struct jpeg_encode_cfg_t {unsigned width,height,src_type,sub_sample,image_quality;};
inline void* jpeg_alloc_encoder_mem(size_t bytes,const jpeg_encode_memory_alloc_cfg_t*,size_t* size) {*size=bytes;return allocate(bytes);}
inline int jpeg_new_encoder_engine(const jpeg_encode_engine_cfg_t*,jpeg_encoder_handle_t* engine) {
    if (fail_allocation()) return ESP_ERR_NO_MEM;
    ++live_engines;*engine=reinterpret_cast<void*>(1);return ESP_OK;
}
inline int jpeg_del_encoder_engine(jpeg_encoder_handle_t engine) {
    assert(engine && !codec_live.load());--live_engines;return ESP_OK;
}
inline unsigned encoded_bytes=100;inline bool damage_source=false;inline int codec_result=ESP_OK;
inline int jpeg_encode_guarded(jpeg_encoder_handle_t,const jpeg_encode_cfg_t*,const uint8_t* raw,uint32_t,
                              uint8_t* output,uint32_t capacity,uint32_t* size) {
    codec_live.store(true);
    while (hold_codec.load()) std::this_thread::yield();
    assert(encoded_bytes<=capacity);std::memset(output,23,encoded_bytes);*size=encoded_bytes;
    if (damage_source) const_cast<uint8_t*>(raw)[0]^=1;
    codec_live.store(false);
    return codec_result;
}
inline bool jpeg_arm_queue_timeout_fixture() {return false;}
inline int mbedtls_sha256(const uint8_t* bytes,size_t size,unsigned char result[32],int) {
    uint32_t hash=2166136261u;for(size_t i=0;i<size;++i) hash=(hash^bytes[i])*16777619u;
    for(unsigned i=0;i<32;++i) result[i]=hash>>(8*(i%4));return 0;
}

struct cJSON {std::vector<cJSON*> children;~cJSON(){for(auto* p:children) delete p;}};
inline cJSON* cJSON_CreateObject() {return new cJSON;}
inline void cJSON_AddItemToArray(cJSON* parent,cJSON* child) {parent->children.push_back(child);}
inline cJSON* cJSON_AddArrayToObject(cJSON* parent,const char*) {auto* child=new cJSON;parent->children.push_back(child);return child;}
inline void cJSON_AddNumberToObject(cJSON*,const char*,double) {}
inline void cJSON_AddStringToObject(cJSON*,const char*,const char*) {}
inline cJSON* diagnostic_event(const char*) {return new cJSON;}
inline void diagnostic_emit(cJSON* event) {delete event;}
inline void diagnostic_check(const char*,const char*,const char*) {}
inline unsigned exported_images=0;
inline bool export_diagnostic_capture(const char*,const unsigned char*,size_t,cJSON* event) {
    ++exported_images;delete event;return true;
}
