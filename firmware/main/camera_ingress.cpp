#include "camera_ingress.h"
#include "esp_cam_ctlr.h"
#include "esp_attr.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"

static DRAM_ATTR portMUX_TYPE counter_lock=portMUX_INITIALIZER_UNLOCKED;
static DRAM_ATTR CameraIngressSnapshot counters;
static DRAM_ATTR esp_cam_ctlr_evt_cbs_t original;
static void* original_data;
static DRAM_ATTR const void* next_destination=nullptr;
struct BufferRecord {const void* pointer=nullptr;CameraFrameEvidence frame;};
static DRAM_ATTR BufferRecord buffers[8];

static bool IRAM_ATTR requested(esp_cam_ctlr_handle_t handle,esp_cam_ctlr_trans_t* trans,void*) {
    bool yield=original.on_get_new_trans ? original.on_get_new_trans(handle,trans,original_data):false;
    portENTER_CRITICAL_SAFE(&counter_lock);
    ++counters.requests;
    next_destination=trans->buffer;
    if (!trans->buffer || !counters.expected_bytes || trans->buflen<counters.expected_bytes) ++counters.missing_buffers;
    portEXIT_CRITICAL_SAFE(&counter_lock);
    return yield; // Callback bool is a scheduler hint, not buffer availability.
}
static bool IRAM_ATTR finished(esp_cam_ctlr_handle_t handle,esp_cam_ctlr_trans_t* trans,void*) {
    portENTER_CRITICAL_SAFE(&counter_lock);
    ++counters.finished;counters.bytes+=trans->received_size;
    // Pinned CSI selects and starts the next DMA destination BEFORE this call.
    // With backup disabled, esp_video reuses its current element on queue
    // starvation and suppresses DONE_BUF when these pointers match.
    if (trans->buffer && trans->buffer==next_destination) ++counters.reused_completions;
    BufferRecord* target=nullptr;
    for (auto& entry:buffers) if (entry.pointer==trans->buffer) {target=&entry;break;}
    if (!target) for (auto& entry:buffers) if (!entry.pointer) {target=&entry;break;}
    if (target && trans->buffer) {
        target->pointer=trans->buffer;
        target->frame={counters.finished,esp_timer_get_time(),trans->received_size};
    } else ++counters.untracked_buffers;
    portEXIT_CRITICAL_SAFE(&counter_lock);
    return original.on_trans_finished ? original.on_trans_finished(handle,trans,original_data):false;
}
extern "C" esp_err_t __real_esp_cam_ctlr_register_event_callbacks(esp_cam_ctlr_handle_t,const esp_cam_ctlr_evt_cbs_t*,void*);
extern "C" esp_err_t __wrap_esp_cam_ctlr_register_event_callbacks(esp_cam_ctlr_handle_t handle,const esp_cam_ctlr_evt_cbs_t* callbacks,void* data) {
    if (!callbacks) return __real_esp_cam_ctlr_register_event_callbacks(handle,callbacks,data);
    // One sequential CSI owner; registration occurs while its controller is stopped.
    const auto previous=original;void* previous_data=original_data;
    original=*callbacks;original_data=data;
    // Old controller has stopped; retain lifetime counts but release pointer identities.
    for (auto& entry:buffers) entry={};
    next_destination=nullptr;
    esp_cam_ctlr_evt_cbs_t observed{requested,finished};
    auto result=__real_esp_cam_ctlr_register_event_callbacks(handle,&observed,nullptr);
    if (result!=ESP_OK) {original=previous;original_data=previous_data;}
    return result;
}
CameraIngressSnapshot camera_ingress_snapshot() {
    portENTER_CRITICAL_SAFE(&counter_lock);
    auto snapshot=counters;
    portEXIT_CRITICAL_SAFE(&counter_lock);
    return snapshot;
}
void configure_camera_ingress(size_t expected_bytes) {
    portENTER_CRITICAL_SAFE(&counter_lock);
    counters.expected_bytes=expected_bytes;
    portEXIT_CRITICAL_SAFE(&counter_lock);
}
bool camera_frame_evidence(const void* pointer,CameraFrameEvidence& evidence) {
    bool found=false;
    portENTER_CRITICAL_SAFE(&counter_lock);
    for (const auto& entry:buffers) if (pointer && entry.pointer==pointer) {
        evidence=entry.frame;found=true;break;
    }
    portEXIT_CRITICAL_SAFE(&counter_lock);
    return found;
}

bool camera_owns_video(const void* video) {return video && video==original_data;}
