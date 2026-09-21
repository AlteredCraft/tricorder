#include "jpeg_pipeline.h"
#include "owned_frame.h"
#include "diagnostic_events.h"
#include "media.h"
#include "driver/jpeg_encode.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "mbedtls/sha256.h"
#include <atomic>
#include <cstdlib>
#include <cstdio>
#include <cstring>
#include <new>

static bool digest(const uint8_t* bytes,size_t size,char hex[65]) {
    unsigned char result[32];
    if (mbedtls_sha256(bytes,size,result,0)) return false;
    for (unsigned i=0;i<32;++i) snprintf(hex+i*2,3,"%02x",result[i]);
    return true;
}
struct JpegRecord {
    FrameStamp stamp{};
    char copied_hash[65]{},after_hash[65]{};
    int64_t started=0,ended=0;
    size_t offset=0,size=0;
    esp_err_t result=ESP_FAIL;
};
struct JpegPipeline::State {
    static constexpr size_t pool_capacity=6*1024*1024;
    unsigned width,height,attempts=0,busy_drops=0,pool_overflows=0;
    size_t bytes,output_capacity=0,used=0;
    uint8_t* input=nullptr;uint8_t* output=nullptr;uint8_t* pool=nullptr;
    JpegRecord* records=nullptr;OwnedFrame* slot=nullptr;
    jpeg_encoder_handle_t engine=nullptr;
    TaskHandle_t worker=nullptr;SemaphoreHandle_t done=nullptr;
    std::atomic<bool> stopping{false};int64_t epoch=0;
    State(unsigned w,unsigned h):width(w),height(h),bytes(size_t(w)*h*2) {}
    bool initialize() {
        if (!width || !height || width>1600 || height>1600) return false;
        input=static_cast<uint8_t*>(heap_caps_malloc(bytes,MALLOC_CAP_SPIRAM));
        jpeg_encode_memory_alloc_cfg_t memory{};memory.buffer_direction=JPEG_ENC_ALLOC_OUTPUT_BUFFER;
        output=static_cast<uint8_t*>(jpeg_alloc_encoder_mem(bytes,&memory,&output_capacity));
        pool=static_cast<uint8_t*>(heap_caps_malloc(pool_capacity,MALLOC_CAP_SPIRAM));
        records=static_cast<JpegRecord*>(heap_caps_calloc(30,sizeof(JpegRecord),MALLOC_CAP_SPIRAM));
        done=xSemaphoreCreateBinary();
        if (!input || !output || !pool || !records || !done) return false;
        for (unsigned i=0;i<30;++i) new(records+i) JpegRecord();
        slot=new(std::nothrow) OwnedFrame(input,bytes);
        if (!slot) return false;
        jpeg_encode_engine_cfg_t config{};config.timeout_ms=500;
        if (jpeg_new_encoder_engine(&config,&engine)!=ESP_OK) return false;
        return xTaskCreate(task,"jpeg",8192,this,5,&worker)==pdPASS;
    }
    static void task(void* argument) {
        auto& self=*static_cast<State*>(argument);
        for (;;) {
            ulTaskNotifyTake(pdTRUE,portMAX_DELAY);
            if (self.stopping.load()) break;
            const uint8_t* raw=nullptr;FrameStamp stamp;
            if (!self.slot->acquire(raw,stamp)) continue;
            auto& r=self.records[stamp.index-1];r.stamp=stamp;
            r.started=esp_timer_get_time();
            bool copied=digest(raw,self.bytes,r.copied_hash) && strcmp(r.copied_hash,stamp.source_sha256)==0;
            jpeg_encode_cfg_t config{};config.width=self.width;config.height=self.height;
            config.src_type=JPEG_ENCODE_IN_FORMAT_RGB565;config.sub_sample=JPEG_DOWN_SAMPLING_YUV420;config.image_quality=75;
            uint32_t size=0;
            r.result=copied ? jpeg_encoder_process(self.engine,&config,raw,self.bytes,self.output,self.output_capacity,&size):ESP_FAIL;
            if (!digest(raw,self.bytes,r.after_hash) || strcmp(r.after_hash,stamp.source_sha256)) r.result=ESP_FAIL;
            if (r.result==ESP_OK && (!size || size>self.output_capacity)) r.result=ESP_ERR_INVALID_SIZE;
            if (r.result==ESP_OK && size>pool_capacity-self.used) {++self.pool_overflows;r.result=ESP_ERR_NO_MEM;}
            if (r.result==ESP_OK) {
                r.offset=self.used;r.size=size;memcpy(self.pool+self.used,self.output,size);self.used+=size;
            }
            r.ended=esp_timer_get_time();
            self.slot->release();
        }
        xSemaphoreGive(self.done);
        vTaskDelete(nullptr); // No State access after the completion signal.
    }
    ~State() {
        if (worker) {
            stopping.store(true);xTaskNotifyGive(worker);
            configASSERT(xSemaphoreTake(done,pdMS_TO_TICKS(2000))==pdTRUE);
        }
        if (engine) jpeg_del_encoder_engine(engine);
        if (done) vSemaphoreDelete(done);
        delete slot;free(input);free(output);free(pool);free(records);
    }
};
JpegPipeline::JpegPipeline(unsigned width,unsigned height) {
    state_=new(std::nothrow) State(width,height);
    if (state_ && !state_->initialize()) {delete state_;state_=nullptr;}
}
JpegPipeline::~JpegPipeline() {if (state_) {wait_idle();delete state_;}}
bool JpegPipeline::ready() const {return state_!=nullptr;}
void JpegPipeline::begin(int64_t epoch) {if (state_) state_->epoch=epoch;}
bool JpegPipeline::submit(const uint8_t* source,size_t bytes,const CameraFrameEvidence& frame,int64_t dequeued) {
    if (!state_ || state_->attempts>=30) return false;
    auto& s=*state_;auto& record=s.records[s.attempts++];
    FrameStamp stamp;stamp.index=s.attempts;stamp.sequence=frame.sequence;stamp.completed=frame.finished_us;stamp.dequeued=dequeued;
    record.stamp=stamp;record.result=ESP_FAIL;
    if (!s.slot->idle()) {++s.busy_drops;return false;}
    if (bytes!=s.bytes || !source) return false;
    stamp.source_hash_start=esp_timer_get_time();
    if (!digest(source,bytes,stamp.source_sha256)) return false;
    stamp.source_hash_end=esp_timer_get_time();
    stamp.copy_start=esp_timer_get_time();
    if (!s.slot->copy(source,bytes,stamp,esp_timer_get_time)) {++s.busy_drops;return false;}
    return true;
}
void JpegPipeline::dispatch() {if (state_) xTaskNotifyGive(state_->worker);}
void JpegPipeline::wait_idle() {
    if (!state_) return;
    const int64_t deadline=esp_timer_get_time()+2000000;
    while (!state_->slot->idle() && esp_timer_get_time()<deadline) vTaskDelay(1);
    configASSERT(state_->slot->idle()); // Never free a DMA/worker-owned buffer after a stalled job.
}
bool JpegPipeline::export_results(const char* boot_id) {
    if (!state_) return false;
    wait_idle();auto& s=*state_;bool ok=s.attempts==30 && !s.busy_drops && !s.pool_overflows;
    auto* meta=diagnostic_event("jpeg_baseline");
    cJSON_AddNumberToObject(meta,"width",s.width);cJSON_AddNumberToObject(meta,"height",s.height);
    cJSON_AddNumberToObject(meta,"quality",75);cJSON_AddStringToObject(meta,"subsampling","YUV420");
    cJSON_AddStringToObject(meta,"timing_scope","encode start/end include copy-proof hashing, codec, post-hash and bounded retention copy");
    cJSON_AddStringToObject(meta,"source_format","rgb565le");cJSON_AddNumberToObject(meta,"source_bytes",s.bytes);
    cJSON_AddNumberToObject(meta,"epoch_start_us",s.epoch);cJSON_AddNumberToObject(meta,"attempts",s.attempts);
    cJSON_AddNumberToObject(meta,"busy_drops",s.busy_drops);cJSON_AddNumberToObject(meta,"pool_overflows",s.pool_overflows);
    cJSON_AddNumberToObject(meta,"output_capacity",s.output_capacity);cJSON_AddNumberToObject(meta,"pool_capacity",s.pool_capacity);
    auto* records=cJSON_AddArrayToObject(meta,"records");
    for (unsigned i=0;i<s.attempts;++i) {
        const auto& r=s.records[i];auto* row=cJSON_CreateObject();
        cJSON_AddNumberToObject(row,"index",i+1);cJSON_AddNumberToObject(row,"source_sequence",r.stamp.sequence);
        cJSON_AddNumberToObject(row,"source_completed_us",r.stamp.completed-s.epoch);
        cJSON_AddNumberToObject(row,"dequeued_us",r.stamp.dequeued-s.epoch);cJSON_AddNumberToObject(row,"copied_us",r.stamp.copied-s.epoch);
        cJSON_AddNumberToObject(row,"source_hash_start_us",r.stamp.source_hash_start-s.epoch);
        cJSON_AddNumberToObject(row,"source_hash_end_us",r.stamp.source_hash_end-s.epoch);
        cJSON_AddNumberToObject(row,"copy_start_us",r.stamp.copy_start-s.epoch);
        cJSON_AddNumberToObject(row,"encode_start_us",r.started-s.epoch);cJSON_AddNumberToObject(row,"encode_end_us",r.ended-s.epoch);
        cJSON_AddStringToObject(row,"source_sha256",r.stamp.source_sha256);cJSON_AddStringToObject(row,"copy_sha256",r.copied_hash);
        cJSON_AddStringToObject(row,"after_sha256",r.after_hash);cJSON_AddNumberToObject(row,"jpeg_bytes",r.size);
        cJSON_AddNumberToObject(row,"result",r.result);cJSON_AddItemToArray(records,row);
        ok=ok && r.result==ESP_OK && r.size>0;
    }
    diagnostic_emit(meta);
    for (unsigned i=0;i<s.attempts;++i) {
        const auto& r=s.records[i];if (!r.size) continue;
        auto* image=diagnostic_event("capture_start");
        cJSON_AddStringToObject(image,"format","jpeg");cJSON_AddNumberToObject(image,"width",s.width);cJSON_AddNumberToObject(image,"height",s.height);
        cJSON_AddNumberToObject(image,"source_sequence",r.stamp.sequence);cJSON_AddStringToObject(image,"source_sha256",r.stamp.source_sha256);
        cJSON_AddNumberToObject(image,"source_completed_device_us",r.stamp.completed);
        cJSON_AddNumberToObject(image,"quality",75);cJSON_AddStringToObject(image,"subsampling","YUV420");
        char id[80];snprintf(id,sizeof(id),"%s-jpeg-%u",boot_id,i+1);
        ok=export_diagnostic_capture(id,s.pool+r.offset,r.size,image) && ok;
    }
    diagnostic_check("jpeg_baseline",ok ? "pass":"fail","Thirty fresh owned-frame encodes; independent decode, provenance and timing checks required.");
    return ok;
}
