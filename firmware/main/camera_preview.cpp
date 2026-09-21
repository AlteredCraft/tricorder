#include "camera_preview.h"
#include "preview_queue.h"
#include "ui_ingress.h"
#include "diagnostic_events.h"
#include "media.h"
#include "bsp/m5stack_tab5.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include <cstdlib>
#include <cstdio>
#include <new>

// Source release is safe only because the pinned LVGL SW renderer executes
// synchronously inside lv_timer_handler under the BSP lock. Panel DMA reads
// separate LVGL draw buffers, not the preview source. Re-review on renderer changes.
#if LV_USE_OS != LV_OS_NONE || LV_DRAW_SW_DRAW_UNIT_CNT != 1
#error Camera preview source lifetime requires the pinned synchronous LVGL renderer
#endif

struct PreviewFrameRow {int64_t index,sequence,completed,dequeued,copy_start,copy_end,selected,result;};
static_assert(sizeof(PreviewFrameRow)==8*sizeof(int64_t));
struct CameraPreview::State {
    static constexpr unsigned width=640,height=360,capacity=2048;
    static constexpr size_t bytes=size_t(width)*height*2,submission_capacity=8192;
    PreviewQueue queue;
    uint16_t* pixels[3]{};lv_image_dsc_t images[3]{};
    PreviewFrameRow* frames=nullptr;UiSubmissionRow* submissions=nullptr;UiIngress* log=nullptr;
    lv_obj_t* root=nullptr;lv_obj_t* image=nullptr;lv_obj_t* status=nullptr;lv_timer_t* timer=nullptr;
    unsigned attempts=0,busy=0,copy_errors=0;
    int64_t epoch=0,ended=0;int last=-1;bool observing=false,finished=false;
    bool initialize(unsigned source_width,unsigned source_height) {
        if (source_width!=width*2 || source_height!=height*2) return false;
        for (auto& p:pixels) {p=static_cast<uint16_t*>(heap_caps_calloc(1,bytes,MALLOC_CAP_SPIRAM));if (!p) return false;}
        frames=static_cast<PreviewFrameRow*>(heap_caps_calloc(capacity,sizeof(PreviewFrameRow),MALLOC_CAP_SPIRAM));
        submissions=static_cast<UiSubmissionRow*>(heap_caps_malloc(submission_capacity*sizeof(UiSubmissionRow),MALLOC_CAP_SPIRAM));
        if (!frames || !submissions) return false;
        configASSERT(bsp_display_lock(0));
        root=lv_obj_create(lv_screen_active());lv_obj_remove_style_all(root);
        lv_obj_set_size(root,1280,720);lv_obj_set_pos(root,0,0);
        lv_obj_set_style_bg_color(root,lv_color_hex(0xDBE4EE),0);lv_obj_set_style_bg_opa(root,LV_OPA_COVER,0);
        lv_obj_remove_flag(root,LV_OBJ_FLAG_SCROLLABLE);
        auto text=[&](const char* value,int x,int y,const lv_font_t* font) {
            auto* label=lv_label_create(root);lv_obj_set_pos(label,x,y);lv_label_set_text(label,value);
            lv_obj_set_style_text_font(label,font,0);lv_obj_set_style_text_color(label,lv_color_hex(0x243B53),0);
            return label;
        };
        text("Camera preview",48,42,&lv_font_montserrat_40);
        text("Live view, with an owned JPEG snapshot every two seconds",48,101,&lv_font_montserrat_24);
        image=lv_image_create(root);lv_obj_set_pos(image,48,188);
        for (unsigned i=0;i<3;++i) {
            auto& d=images[i];d.header.magic=LV_IMAGE_HEADER_MAGIC;d.header.cf=LV_COLOR_FORMAT_RGB565;
            d.header.w=width;d.header.h=height;d.header.stride=width*2;d.data_size=bytes;
            d.data=reinterpret_cast<const uint8_t*>(pixels[i]);
        }
        lv_image_set_src(image,&images[0]);
        lv_obj_add_flag(image,LV_OBJ_FLAG_HIDDEN); // Slot zero is still producer-free until first selection.
        text("Native capture",744,194,&lv_font_montserrat_28);
        text("1280 x 720 at 30 fps",744,240,&lv_font_montserrat_24);
        text("Preview",744,319,&lv_font_montserrat_28);
        text("640 x 360, every other frame",744,365,&lv_font_montserrat_24);
        status=text("Waiting for a frame",744,444,&lv_font_montserrat_24);
        lv_obj_set_style_text_color(status,lv_color_hex(0x1E6F9F),0);
        text("Older pending previews may be replaced. Measurement loss is still a failure.",48,600,&lv_font_montserrat_22);
        text("Automatic 60-second check; no touch input needed yet.",48,644,&lv_font_montserrat_20);
        lv_refr_now(lv_display_get_default());bsp_display_unlock();return true;
    }
    static void tick(lv_timer_t* timer) {static_cast<State*>(lv_timer_get_user_data(timer))->select();}
    void select() { // LVGL task or explicit final drain, always under display lock.
        const int next=queue.take_latest();if (next<0) return;
        const auto generation=queue.generation(next);auto& row=frames[generation-1];
        row.selected=esp_timer_get_time()-epoch;last=next;
        lv_image_cache_drop(&images[next]);lv_image_set_src(image,&images[next]);lv_obj_invalidate(image);
        lv_obj_remove_flag(image,LV_OBJ_FLAG_HIDDEN);
        lv_label_set_text_fmt(status,"Source frame %lu",static_cast<unsigned long>(row.sequence));
        log->animation(generation,epoch+row.selected);
        if (!observing) {ui_observe(log);observing=true;}
    }
    static void display_event(lv_event_t* event) {
        auto& self=*static_cast<State*>(lv_event_get_user_data(event));if (!self.observing) return;
        switch (lv_event_get_code(event)) {
            case LV_EVENT_RENDER_START:self.log->render();break;
            case LV_EVENT_FLUSH_START:self.log->flush(lv_display_flush_is_last(lv_display_get_default()));break;
            default:break;
        }
    }
    void begin(int64_t start) {
        epoch=start;log=new(std::nothrow) UiIngress(submissions,submission_capacity,epoch);configASSERT(log);
        configASSERT(bsp_display_lock(0));
        auto* display=lv_display_get_default();lv_timer_set_period(lv_display_get_refr_timer(display),20);
        lv_display_add_event_cb(display,display_event,LV_EVENT_ALL,this);
        timer=lv_timer_create(tick,10,this);configASSERT(timer);bsp_display_unlock();
        // Creating a timer from another task does not interrupt the port's
        // previously calculated idle wait (up to 500 ms).
        configASSERT(lvgl_port_task_wake(LVGL_PORT_EVENT_USER,nullptr)==ESP_OK);
    }
    void finish() {
        if (finished) return;
        configASSERT(bsp_display_lock(0));
        if (timer) {lv_timer_delete(timer);timer=nullptr;select();lv_refr_now(lv_display_get_default());}
        ended=esp_timer_get_time();
        if (observing) {ui_observe(nullptr);observing=false;}
        if (log) {
            auto* display=lv_display_get_default();lv_display_remove_event_cb_with_user_data(display,display_event,this);
            lv_timer_set_period(lv_display_get_refr_timer(display),LV_DEF_REFR_PERIOD);
        }
        if (root) {lv_obj_delete(root);root=nullptr;}
        for (auto& d:images) lv_image_cache_drop(&d);
        queue.release_display();finished=true;bsp_display_unlock();
    }
    ~State() {if (root) finish();delete log;for(auto* p:pixels)free(p);free(frames);free(submissions);}
};

CameraPreview::CameraPreview(unsigned width,unsigned height) {
    state_=new(std::nothrow) State;
    if (state_ && !state_->initialize(width,height)) {delete state_;state_=nullptr;}
}
CameraPreview::~CameraPreview() {delete state_;}
bool CameraPreview::ready() const {return state_!=nullptr;}
void CameraPreview::begin(int64_t epoch) {if(state_)state_->begin(epoch);}
void CameraPreview::finish() {if(state_)state_->finish();}
bool CameraPreview::offer(const uint8_t* source,size_t bytes,const CameraFrameEvidence& frame,int64_t dequeued) {
    if (!state_ || state_->finished || state_->attempts==State::capacity) return false;
    auto& s=*state_;auto& r=s.frames[s.attempts++];r.index=s.attempts;r.sequence=frame.sequence;
    r.completed=frame.finished_us-s.epoch;r.dequeued=dequeued-s.epoch;r.result=-1;
    const int i=s.queue.begin_write();if(i<0) {++s.busy;return false;}
    r.copy_start=esp_timer_get_time()-s.epoch;
    bool ok=preview_half_rgb565(reinterpret_cast<const uint16_t*>(source),bytes,State::width*2,State::height*2,s.pixels[i],State::bytes);
    r.copy_end=esp_timer_get_time()-s.epoch;
    if (!ok) {++s.copy_errors;s.queue.cancel_write(i);return false;}
    r.result=0;s.queue.publish(i,s.attempts);return true;
}
bool CameraPreview::export_results(const char* boot_id,size_t camera_frames) {
    if (!state_) return false;
    finish();auto& s=*state_;
    auto* meta=diagnostic_event("capture_start");
    cJSON_AddStringToObject(meta,"format","preview_frames_i64le");
    cJSON_AddStringToObject(meta,"layout","index,source_sequence,completed_us,dequeued_us,copy_start_us,copy_end_us,selected_us,result; relative epoch; selected=0 means replaced before selection");
    cJSON_AddStringToObject(meta,"policy","every second camera row; three owned buffers; replace only pending preview; display holds its source between renders");
    cJSON_AddStringToObject(meta,"resize","nearest RGB565 top-left pixel of each 2x2 source block");
    cJSON_AddNumberToObject(meta,"rows",s.attempts);cJSON_AddNumberToObject(meta,"columns",8);
    cJSON_AddNumberToObject(meta,"width",State::width);cJSON_AddNumberToObject(meta,"height",State::height);
    cJSON_AddNumberToObject(meta,"buffer_count",3);cJSON_AddNumberToObject(meta,"buffer_bytes",State::bytes);
    cJSON_AddNumberToObject(meta,"camera_frames",camera_frames);cJSON_AddNumberToObject(meta,"throttled_frames",camera_frames-s.attempts);
    cJSON_AddNumberToObject(meta,"produced",s.queue.produced());cJSON_AddNumberToObject(meta,"selected",s.queue.selected());
    cJSON_AddNumberToObject(meta,"pending_replaced",s.queue.replaced());cJSON_AddNumberToObject(meta,"pending_end",s.queue.pending());
    cJSON_AddNumberToObject(meta,"busy_drops",s.busy);cJSON_AddNumberToObject(meta,"copy_errors",s.copy_errors);
    cJSON_AddNumberToObject(meta,"acquisition_start_us",s.epoch);cJSON_AddNumberToObject(meta,"duration_us",s.ended-s.epoch);
    char id[96];snprintf(id,sizeof(id),"%s-preview-frames",boot_id);
    bool ok=s.attempts && s.log && !s.busy && !s.copy_errors && !s.queue.pending();
    if (s.attempts) ok=export_diagnostic_capture(id,reinterpret_cast<const uint8_t*>(s.frames),s.attempts*sizeof(PreviewFrameRow),meta) && ok;
    else cJSON_Delete(meta);
    auto* ui=diagnostic_event("capture_start");cJSON_AddStringToObject(ui,"format","preview_submissions_i64le");
    cJSON_AddNumberToObject(ui,"columns",11);cJSON_AddNumberToObject(ui,"rows",s.log ? s.log->count():0);
    cJSON_AddNumberToObject(ui,"renders",s.log ? s.log->renders():0);cJSON_AddNumberToObject(ui,"observer_overflow",s.log ? s.log->overflow():0);
    cJSON_AddNumberToObject(ui,"acquisition_start_us",s.epoch);cJSON_AddNumberToObject(ui,"duration_us",s.ended-s.epoch);
    snprintf(id,sizeof(id),"%s-preview-submissions",boot_id);
    if(s.log && s.log->count()) ok=export_diagnostic_capture(id,reinterpret_cast<const uint8_t*>(s.submissions),s.log->count()*sizeof(UiSubmissionRow),ui) && !s.log->overflow() && ok;
    else {cJSON_Delete(ui);ok=false;}
    if (s.last>=0) {
        auto* image=diagnostic_event("capture_start");cJSON_AddStringToObject(image,"format","rgb565le");
        cJSON_AddNumberToObject(image,"width",State::width);cJSON_AddNumberToObject(image,"height",State::height);
        cJSON_AddNumberToObject(image,"source_sequence",s.frames[s.queue.generation(s.last)-1].sequence);
        snprintf(id,sizeof(id),"%s-preview-last",boot_id);
        ok=export_diagnostic_capture(id,reinterpret_cast<const uint8_t*>(s.pixels[s.last]),State::bytes,image) && ok;
    } else ok=false;
    diagnostic_check("camera_preview",ok ? "pass":"fail","Owned preview queue and panel submissions; independent chronology, timing and raw witness assessment required.");
    return ok;
}
