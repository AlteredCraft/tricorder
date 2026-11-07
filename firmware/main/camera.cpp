#include "camera.h"
#include "media.h"
#include "image_downsample.h"
#include "jpeg_guard.h"
#include "diagnostic_events.h"
#include "home.h"
#include "investigation.h"
#include "bsp/m5stack_tab5.h"
#include "driver/jpeg_encode.h"
#include "esp_heap_caps.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "mbedtls/sha256.h"
#include <atomic>
#include <cstdio>
#include <cstring>
#include <string>

namespace {
QueueHandle_t media;
std::atomic<bool> stop{true},photo_requested{false},explaining{false};
// Live view: the media owner writes the buffer the screen is not showing, then marks it
// pending; the LVGL timer shows it and clears pending. Nothing is written while pending.
constexpr unsigned view_w=640,view_h=360;constexpr size_t view_bytes=size_t(view_w)*view_h*2;
uint16_t* view[2];lv_image_dsc_t view_dsc[2];
std::atomic<int> pending{-1},shown{0};
std::atomic<const char*> notice{nullptr}; // media owner -> LVGL timer, shown once
// The photo: the media owner fills these, then sets photo_state.
enum PhotoState {NoPhoto,Taking,Ready,Failed};
std::atomic<int> photo_state{NoPhoto};
uint8_t* photo_raw;size_t photo_raw_capacity;unsigned photo_w,photo_h;
uint8_t* photo_jpeg;size_t photo_jpeg_capacity;uint32_t photo_jpeg_size;char photo_sha[65];
jpeg_encoder_handle_t encoder;
unsigned frames=0,view_frames=0;
lv_obj_t *panel,*image,*status_label,*hint_label,*reply_label,*photo_label,*photo_button,*explain_label,*explain_button;
int photo_drawn=NoPhoto; // LVGL task

void log_control(const char* control) {
    auto* e=diagnostic_event("camera_control");cJSON_AddStringToObject(e,"control",control);
    cJSON_AddNumberToObject(e,"view_frames",view_frames);cJSON_AddNumberToObject(e,"photo_state",photo_state.load());
    diagnostic_emit(e);
}
void send_media(uint8_t command) {
    if(xQueueSend(media,&command,0)!=pdTRUE) {
        auto* e=diagnostic_event("camera_session");cJSON_AddStringToObject(e,"result","queue_full");
        cJSON_AddNumberToObject(e,"command",command);diagnostic_emit(e);
    }
}
void draw(lv_timer_t*) {
    if(lv_obj_has_flag(panel,LV_OBJ_FLAG_HIDDEN))return;
    const int next=pending.load();
    if(next>=0) {
        lv_image_cache_drop(&view_dsc[next]);lv_image_set_src(image,&view_dsc[next]);lv_obj_invalidate(image);
        lv_obj_remove_flag(image,LV_OBJ_FLAG_HIDDEN);
        shown.store(next);pending.store(-1);++view_frames;
        if(view_frames==1 && photo_state.load()==NoPhoto)lv_label_set_text(status_label,"Live. Point the camera, then tap Take photo.");
    }
    if(const char* text=notice.exchange(nullptr))lv_label_set_text(status_label,text);
    const int state=photo_state.load();
    if(state==photo_drawn)return;
    photo_drawn=state;
    if(state==Ready) {
        char text[96];snprintf(text,sizeof(text),"Photo taken, %u KB. Tap Explain to ask what it shows.",unsigned(photo_jpeg_size/1024));
        lv_label_set_text(status_label,text);lv_label_set_text(photo_label,"Retake");
        lv_obj_remove_state(explain_button,LV_STATE_DISABLED);lv_obj_remove_state(photo_button,LV_STATE_DISABLED);
    } else if(state==Failed) {
        lv_label_set_text(status_label,"The photo could not be taken. Tap Retake to try again.");
        lv_label_set_text(photo_label,"Retake");lv_obj_remove_state(photo_button,LV_STATE_DISABLED);
    }
}
void photo_clicked(lv_event_t*) {
    const int state=photo_state.load();
    if(state==Ready || state==Failed) {
        investigation_stop_speech();log_control("retake");camera_ui_open();return;
    }
    if(state!=NoPhoto || !view_frames)return;
    photo_state.store(Taking);photo_drawn=Taking;photo_requested.store(true);
    lv_label_set_text(status_label,"Hold still...");lv_obj_add_state(photo_button,LV_STATE_DISABLED);
    log_control("take_photo");
}
// Explain: while the agent answers or speaks, the button stops the voice.
void explain_clicked(lv_event_t*) {
    if(explaining.load()){investigation_stop_speech();log_control("explain_stop_voice");return;}
    if(photo_state.load()!=Ready)return;
    explaining.store(true);lv_label_set_text(explain_label,"Stop voice");
    lv_obj_add_state(photo_button,LV_STATE_DISABLED);
    log_control("explain");send_media(camera_explain_command);
}
void back(lv_event_t*) {
    stop.store(true);investigation_stop_speech();
    lv_obj_add_flag(panel,LV_OBJ_FLAG_HIDDEN);log_control("back");home_returned("camera");
}
lv_obj_t* text(lv_obj_t* parent,const char* value,int x,int y,const lv_font_t* font,uint32_t color) {
    auto* l=lv_label_create(parent);lv_label_set_text(l,value);lv_obj_set_pos(l,x,y);
    lv_obj_set_style_text_font(l,font,0);lv_obj_set_style_text_color(l,lv_color_hex(color),0);return l;
}
lv_obj_t* button(lv_obj_t* parent,const char* value,int x,lv_event_cb_t callback) {
    auto* b=lv_button_create(parent);lv_obj_set_pos(b,x,14);lv_obj_set_size(b,180,64);
    lv_obj_add_event_cb(b,callback,LV_EVENT_CLICKED,nullptr);
    auto* l=lv_label_create(b);lv_label_set_text(l,value);lv_obj_set_style_text_font(l,&lv_font_montserrat_24,0);lv_obj_center(l);
    return l;
}
}

void camera_ui_init(lv_obj_t* screen,QueueHandle_t media_commands) {
    media=media_commands;
    for(unsigned i=0;i<2;++i) {
        view[i]=static_cast<uint16_t*>(heap_caps_calloc(1,view_bytes,MALLOC_CAP_SPIRAM));
        auto& d=view_dsc[i];d.header.magic=LV_IMAGE_HEADER_MAGIC;d.header.cf=LV_COLOR_FORMAT_RGB565;
        d.header.w=view_w;d.header.h=view_h;d.header.stride=view_w*2;d.data_size=view_bytes;
        d.data=reinterpret_cast<const uint8_t*>(view[i]);
    }
    jpeg_encode_memory_alloc_cfg_t input{};input.buffer_direction=JPEG_ENC_ALLOC_INPUT_BUFFER;
    photo_raw=static_cast<uint8_t*>(jpeg_alloc_encoder_mem(1280*720*2,&input,&photo_raw_capacity));
    jpeg_encode_memory_alloc_cfg_t output{};output.buffer_direction=JPEG_ENC_ALLOC_OUTPUT_BUFFER;
    photo_jpeg=static_cast<uint8_t*>(jpeg_alloc_encoder_mem(512*1024,&output,&photo_jpeg_capacity));
    auto* e=diagnostic_event("camera_init");cJSON_AddBoolToObject(e,"view_buffers",view[0] && view[1]);
    cJSON_AddBoolToObject(e,"photo_buffers",photo_raw && photo_jpeg);cJSON_AddNumberToObject(e,"jpeg_capacity",photo_jpeg_capacity);
    diagnostic_emit(e);

    panel=lv_obj_create(screen);lv_obj_remove_style_all(panel);lv_obj_set_size(panel,1280,720);lv_obj_set_pos(panel,0,0);
    lv_obj_set_style_bg_color(panel,lv_color_hex(0x101418),0);lv_obj_set_style_bg_opa(panel,LV_OPA_COVER,0);
    lv_obj_remove_flag(panel,LV_OBJ_FLAG_SCROLLABLE);
    text(panel,"Camera",24,20,&lv_font_montserrat_40,0xffffff);
    photo_label=button(panel,"Take photo",690,photo_clicked);photo_button=lv_obj_get_parent(photo_label);
    explain_label=button(panel,"Explain",886,explain_clicked);explain_button=lv_obj_get_parent(explain_label);
    button(panel,"Home",1082,back);
    status_label=text(panel,"",24,82,&lv_font_montserrat_20,0x4fc3f7);
    lv_obj_set_width(status_label,1232);lv_label_set_long_mode(status_label,LV_LABEL_LONG_DOT);
    image=lv_image_create(panel);lv_obj_set_pos(image,24,114);lv_obj_set_size(image,view_w,view_h);
    lv_obj_set_style_bg_color(image,lv_color_hex(0x000000),0);lv_obj_set_style_bg_opa(image,LV_OPA_COVER,0);
    hint_label=text(panel,"Live view, half size. The photo is taken at 1280 x 720.",24,484,&lv_font_montserrat_22,0x90a4ae);
    lv_obj_set_width(hint_label,view_w);lv_label_set_long_mode(hint_label,LV_LABEL_LONG_WRAP);
    auto* box=lv_obj_create(panel);lv_obj_set_pos(box,690,114);lv_obj_set_size(box,566,586);
    lv_obj_set_style_bg_color(box,lv_color_hex(0x161c21),0);lv_obj_set_style_border_width(box,0,0);
    lv_obj_set_style_pad_all(box,20,0);lv_obj_set_scroll_dir(box,LV_DIR_VER);
    reply_label=text(box,"",0,0,&lv_font_montserrat_24,0xe0e0e0);
    lv_obj_set_width(reply_label,lv_pct(100));lv_label_set_long_mode(reply_label,LV_LABEL_LONG_WRAP);
    lv_obj_set_style_text_line_space(reply_label,6,0);
    lv_timer_create(draw,50,nullptr);
    lv_obj_add_flag(panel,LV_OBJ_FLAG_HIDDEN);
}

void camera_ui_open() {
    photo_state.store(NoPhoto);photo_drawn=NoPhoto;photo_requested.store(false);view_frames=0;notice.store(nullptr);
    lv_label_set_text(status_label,"Starting the camera...");lv_label_set_text(photo_label,"Take photo");
    lv_label_set_text(explain_label,"Explain");lv_label_set_text(reply_label,"");
    lv_obj_add_state(explain_button,LV_STATE_DISABLED);lv_obj_remove_state(photo_button,LV_STATE_DISABLED);
    lv_obj_add_flag(image,LV_OBJ_FLAG_HIDDEN);
    lv_obj_remove_flag(panel,LV_OBJ_FLAG_HIDDEN);lv_obj_move_foreground(panel);
    stop.store(false);send_media(camera_media_command);
}

namespace {
// Media owner: half-size box average into the free view buffer, when the screen has
// taken the last one.
bool publish_view(const uint16_t* pixels,unsigned w,unsigned h,bool wait) {
    if(w!=2*view_w || h!=2*view_h || !view[0] || !view[1])return false;
    while(pending.load()>=0) {if(!wait)return false;vTaskDelay(1);}
    const int write=1-shown.load();
    if(!rgb565_downsample(pixels,size_t(w)*h*2,w,h,2,view[write],view_bytes))return false;
    pending.store(write);return true;
}
bool on_frame(const uint16_t* pixels,unsigned w,unsigned h,void*) {
    ++frames;
    if(photo_requested.exchange(false)) {
        const size_t bytes=size_t(w)*h*2;
        if(photo_raw && bytes<=photo_raw_capacity) {
            memcpy(photo_raw,pixels,bytes);photo_w=w;photo_h=h;
            publish_view(pixels,w,h,true);
        } else photo_state.store(Failed);
        return false;
    }
    if(frames%3==0)publish_view(pixels,w,h,false);
    return true;
}
void encode_photo() {
    const int64_t started=esp_timer_get_time();esp_err_t result=ESP_FAIL;uint32_t size=0;
    if(!encoder) {jpeg_encode_engine_cfg_t config{};config.timeout_ms=1000;jpeg_new_encoder_engine(&config,&encoder);}
    if(encoder && photo_jpeg) {
        jpeg_encode_cfg_t config{};config.width=photo_w;config.height=photo_h;
        config.src_type=JPEG_ENCODE_IN_FORMAT_RGB565;config.sub_sample=JPEG_DOWN_SAMPLING_YUV420;config.image_quality=80;
        result=jpeg_encode_guarded(encoder,&config,photo_raw,photo_w*photo_h*2,photo_jpeg,photo_jpeg_capacity,&size);
    }
    bool ok=result==ESP_OK && size>0 && size<=photo_jpeg_capacity;
    if(ok) {
        unsigned char digest[32];ok=mbedtls_sha256(photo_jpeg,size,digest,0)==0;
        for(size_t i=0;i<32;++i)snprintf(photo_sha+i*2,3,"%02x",digest[i]);
    }
    photo_jpeg_size=ok?size:0;
    auto* e=diagnostic_event("camera_photo");cJSON_AddBoolToObject(e,"ok",ok);cJSON_AddNumberToObject(e,"result",result);
    cJSON_AddNumberToObject(e,"width",photo_w);cJSON_AddNumberToObject(e,"height",photo_h);
    cJSON_AddNumberToObject(e,"jpeg_bytes",size);cJSON_AddNumberToObject(e,"encode_us",esp_timer_get_time()-started);
    if(ok)cJSON_AddStringToObject(e,"sha256",photo_sha);
    diagnostic_emit(e);
    photo_state.store(ok?Ready:Failed);
}
}

void camera_run() {
    frames=0;const char* error=nullptr;
    const bool ok=camera_stream(stop,on_frame,nullptr,&error);
    if(!ok) {
        auto* e=diagnostic_event("camera_session");cJSON_AddStringToObject(e,"result","stream_failed");
        cJSON_AddStringToObject(e,"error",error?error:"");diagnostic_emit(e);
        notice.store("The camera did not start. Tap Home, then open Camera again.");
        if(photo_state.load()==Taking)photo_state.store(Failed);
        return;
    }
    if(photo_state.load()==Taking)encode_photo();
}

namespace {
void new_session(char* out,size_t size) {
    snprintf(out,size,"ca-%08lx%08lx%08lx%08lx",static_cast<unsigned long>(esp_random()),static_cast<unsigned long>(esp_random()),
             static_cast<unsigned long>(esp_random()),static_cast<unsigned long>(esp_random()));
}
// The summary the Mac checks against the uploaded bytes (tools/camera_explain.py FIELDS).
cJSON* photo_summary() {
    auto* o=cJSON_CreateObject();
    cJSON_AddStringToObject(o,"kind","camera");cJSON_AddStringToObject(o,"format","jpeg");
    cJSON_AddNumberToObject(o,"width",photo_w);cJSON_AddNumberToObject(o,"height",photo_h);
    cJSON_AddNumberToObject(o,"size_bytes",photo_jpeg_size);cJSON_AddStringToObject(o,"sha256",photo_sha);
    return o;
}
// Media task -> screen; takes the display lock for each update.
void explain_progress(const char* stage,const char*,const char* reply) {
    if(!bsp_display_lock(1000))return;
    if(stage)lv_label_set_text(status_label,stage);
    if(reply) {
        const std::string shown_text="Agent: "+std::string(reply);
        lv_label_set_text(reply_label,shown_text.c_str());lv_obj_scroll_to_y(lv_obj_get_parent(reply_label),0,LV_ANIM_OFF);
        lv_label_set_text(status_label,"The agent's reading is on the right. Stop voice ends the speech.");
    }
    bsp_display_unlock();
}
void restore_buttons(const char* status) {
    if(!bsp_display_lock(1000))return;
    lv_label_set_text(status_label,status);lv_label_set_text(explain_label,"Explain");
    for(auto* b:{explain_button,photo_button})lv_obj_remove_state(b,LV_STATE_DISABLED);
    bsp_display_unlock();
}
}

void camera_explain(const char* boot) {
    char session[40];new_session(session,sizeof(session));
    AnalysisExplainHooks hooks{explain_progress};
    AnalysisExplainResult out;
    const bool ok=photo_state.load()==Ready &&
        investigation_explain_analysis(boot,session,nullptr,photo_summary(),hooks,out,photo_jpeg,photo_jpeg_size);
    explaining.store(false);
    restore_buttons(ok?"Tap Explain to ask again, or Retake for another photo.":out.error.empty()?"Take a photo first.":out.error.c_str());
}
