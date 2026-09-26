#include "sound.h"
#include "sound_model.h"
#include "spectrum_display.h"
#include "audio_devices.h"
#include "audio_ingress.h"
#include "diagnostic_events.h"
#include "home.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <memory>

namespace {
QueueHandle_t media;
std::atomic<bool> stop{true};
lv_obj_t *panel,*chart,*level_label,*level_bar,*freeze_label;
lv_chart_series_t *live_series,*peak_series;
// Media owner -> LVGL timer: the latest view, copied under the lock.
portMUX_TYPE view_lock=portMUX_INITIALIZER_UNLOCKED;
float view_db[spectrum_band_count];float view_level=sound::level_floor_db;unsigned view_sequence=0; // view_lock
// LVGL task only.
float peak[spectrum_band_count];unsigned drawn_sequence=0,draws=0;bool frozen=false;

void set_chart(lv_chart_series_t* series,const float* db) {
    for(size_t i=0;i<spectrum_band_count;++i)lv_chart_set_value_by_id(chart,series,i,spectrum_chart_value(db[i]));
}
void clear_peak() {
    sound::reset_peak(peak,spectrum_band_count);
    for(size_t i=0;i<spectrum_band_count;++i)lv_chart_set_value_by_id(chart,peak_series,i,LV_CHART_POINT_NONE);
}
void draw(lv_timer_t*) {
    if(lv_obj_has_flag(panel,LV_OBJ_FLAG_HIDDEN) || frozen)return;
    float db[spectrum_band_count],level;unsigned sequence;
    portENTER_CRITICAL(&view_lock);
    sequence=view_sequence;level=view_level;if(sequence!=drawn_sequence)memcpy(db,view_db,sizeof(db));
    portEXIT_CRITICAL(&view_lock);
    if(sequence==drawn_sequence)return;
    drawn_sequence=sequence;++draws;
    sound::hold_peak(db,peak,spectrum_band_count);
    set_chart(live_series,db);set_chart(peak_series,peak);lv_chart_refresh(chart);
    char text[24];snprintf(text,sizeof(text),"%.0f dB",level);lv_label_set_text(level_label,text);
    lv_bar_set_value(level_bar,static_cast<int32_t>(std::clamp(level,-100.0f,0.0f)),LV_ANIM_OFF);
}
void log_control(const char* control) {
    auto* e=diagnostic_event("sound_control");cJSON_AddStringToObject(e,"control",control);
    cJSON_AddBoolToObject(e,"frozen",frozen);cJSON_AddNumberToObject(e,"draws",draws);diagnostic_emit(e);
}
void freeze(lv_event_t*) {frozen=!frozen;lv_label_set_text(freeze_label,frozen?"Resume":"Freeze");log_control("freeze");}
void reset(lv_event_t*) {clear_peak();lv_chart_refresh(chart);log_control("reset_peak");}
void back(lv_event_t*) {
    stop.store(true);lv_obj_add_flag(panel,LV_OBJ_FLAG_HIDDEN);log_control("back");home_returned("sound");
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

void sound_ui_init(lv_obj_t* screen,QueueHandle_t media_commands) {
    media=media_commands;
    panel=lv_obj_create(screen);lv_obj_remove_style_all(panel);lv_obj_set_size(panel,1280,720);lv_obj_set_pos(panel,0,0);
    lv_obj_set_style_bg_color(panel,lv_color_hex(0x101418),0);lv_obj_set_style_bg_opa(panel,LV_OPA_COVER,0);
    lv_obj_remove_flag(panel,LV_OBJ_FLAG_SCROLLABLE);
    text(panel,"Sound",24,20,&lv_font_montserrat_40,0xffffff);
    level_label=text(panel,"-- dB",200,26,&lv_font_montserrat_32,0x66bb6a);
    level_bar=lv_bar_create(panel);lv_obj_set_pos(level_bar,340,34);lv_obj_set_size(level_bar,300,24);
    lv_bar_set_range(level_bar,-100,0);lv_bar_set_value(level_bar,-100,LV_ANIM_OFF);
    lv_obj_set_style_bg_color(level_bar,lv_color_hex(0x263238),LV_PART_MAIN);
    lv_obj_set_style_bg_color(level_bar,lv_color_hex(0x66bb6a),LV_PART_INDICATOR);
    freeze_label=button(panel,"Freeze",690,freeze);
    button(panel,"Reset peak",886,reset);
    button(panel,"Home",1082,back);

    // 48 log bands, 50 Hz-20 kHz; 0..100 maps floor..ceiling dB (spectrum_display.h).
    constexpr int chart_x=90,chart_y=110,chart_w=1160,chart_h=540;
    chart=lv_chart_create(panel);lv_obj_set_pos(chart,chart_x,chart_y);lv_obj_set_size(chart,chart_w,chart_h);
    lv_chart_set_type(chart,LV_CHART_TYPE_LINE);lv_chart_set_point_count(chart,spectrum_band_count);
    lv_chart_set_range(chart,LV_CHART_AXIS_PRIMARY_Y,0,100);lv_chart_set_div_line_count(chart,5,0);
    lv_obj_set_style_pad_all(chart,0,0);lv_obj_set_style_bg_color(chart,lv_color_hex(0x000000),0);
    lv_obj_set_style_border_color(chart,lv_color_hex(0x37474f),0);
    lv_obj_set_style_line_color(chart,lv_color_hex(0x263238),LV_PART_MAIN);
    lv_obj_set_style_line_width(chart,3,LV_PART_ITEMS);lv_obj_set_style_size(chart,0,0,LV_PART_INDICATOR);
    peak_series=lv_chart_add_series(chart,lv_color_hex(0xffb74d),LV_CHART_AXIS_PRIMARY_Y);
    live_series=lv_chart_add_series(chart,lv_color_hex(0x66bb6a),LV_CHART_AXIS_PRIMARY_Y);
    for(size_t i=0;i<spectrum_band_count;++i)lv_chart_set_value_by_id(chart,live_series,i,LV_CHART_POINT_NONE);
    clear_peak();
    for(int step=0;step<5;++step) {
        char value[16];snprintf(value,sizeof(value),"%d",static_cast<int>(spectrum_ceiling_db)-20*step);
        text(panel,value,20,chart_y+step*(chart_h-1)/4-12,&lv_font_montserrat_22,0x90a4ae);
    }
    text(panel,"dB",20,chart_y+chart_h+12,&lv_font_montserrat_22,0x90a4ae);
    for(float hz:{100.0f,1000.0f,10000.0f}) {
        const float band=std::log(hz/spectrum_band_low_hz)/std::log(spectrum_band_high_hz/spectrum_band_low_hz)*spectrum_band_count-0.5f;
        const int x=chart_x+static_cast<int>(band/(spectrum_band_count-1)*chart_w);
        text(panel,hz<1000?"100 Hz":hz<10000?"1 kHz":"10 kHz",x-36,chart_y+chart_h+12,&lv_font_montserrat_22,0x90a4ae);
    }
    text(panel,"Live",760,chart_y+chart_h+12,&lv_font_montserrat_22,0x66bb6a);
    text(panel,"Peak",840,chart_y+chart_h+12,&lv_font_montserrat_22,0xffb74d);
    lv_timer_create(draw,50,nullptr);
    lv_obj_add_flag(panel,LV_OBJ_FLAG_HIDDEN);
}

void sound_ui_open() {
    frozen=false;lv_label_set_text(freeze_label,"Freeze");draws=0;
    clear_peak();lv_label_set_text(level_label,"-- dB");lv_bar_set_value(level_bar,-100,LV_ANIM_OFF);
    for(size_t i=0;i<spectrum_band_count;++i)lv_chart_set_value_by_id(chart,live_series,i,LV_CHART_POINT_NONE);
    lv_obj_remove_flag(panel,LV_OBJ_FLAG_HIDDEN);lv_obj_move_foreground(panel);
    stop.store(false);
    const uint8_t command=sound_media_command;
    if(xQueueSend(media,&command,0)!=pdTRUE) {
        auto* e=diagnostic_event("sound_session");cJSON_AddStringToObject(e,"result","queue_full");diagnostic_emit(e);
    }
}

void sound_run() {
    constexpr size_t window_frames=spectrum_max_frames,block_frames=1024,warmup_frames=24000;
    struct Work {
        SpectrumWorkspace workspace;float amplitudes[window_frames/2+1];
        sound::Window<window_frames,4> window;int16_t ordered[window_frames*4];int16_t block[block_frames*4];
    };
    // Zeroed: Window is plain data, so all-zero is its empty state.
    std::unique_ptr<Work,decltype(&free)> work(static_cast<Work*>(
        heap_caps_aligned_calloc(16,1,sizeof(Work),MALLOC_CAP_SPIRAM)),free);
    auto mic=diagnostic_microphone();auto speaker=diagnostic_speaker();
    esp_codec_dev_sample_info_t input{};input.sample_rate=48000;input.channel=4;input.bits_per_sample=16;
    auto output=input;output.channel=2;
    // Same codec setup as a measurement capture: speaker opened muted, mic gain 24 dB.
    const bool mic_open=mic && esp_codec_dev_open(mic,&input)==ESP_OK;
    const bool speaker_open=speaker && esp_codec_dev_open(speaker,&output)==ESP_OK;
    bool ok=work && mic_open && speaker_open && esp_codec_dev_set_out_mute(speaker,true)==ESP_OK &&
        esp_codec_dev_set_in_gain(mic,24)==ESP_OK;
    AudioIngressSnapshot before{},after{};
    if(ok)ok=begin_audio_epoch(before);
    const int64_t started=esp_timer_get_time();
    // Codec startup transients last about 0.2 s; drain 0.5 s before showing anything.
    for(size_t done=0;ok && done<warmup_frames && !stop.load();done+=block_frames)
        ok=esp_codec_dev_read(mic,work->block,block_frames*8)==ESP_OK;
    unsigned blocks=0,views=0;uint64_t max_compute_us=0,total_compute_us=0;
    while(ok && !stop.load()) {
        if(esp_codec_dev_read(mic,work->block,block_frames*8)!=ESP_OK){ok=false;break;}
        work->window.push(work->block,block_frames);
        if(++blocks%2 || !work->window.full())continue;
        const int64_t compute=esp_timer_get_time();
        work->window.copy(work->ordered);
        SpectrumResult result;SpectrumBands bands;float db[spectrum_band_count];
        if(!spectrum_pcm16(work->ordered,window_frames,4,0,work->workspace,work->amplitudes,window_frames/2+1,result) ||
           !spectrum_bands_add(work->amplitudes,window_frames,48000,bands)){ok=false;break;}
        spectrum_bands_db(bands,db);
        const float level=sound::level_dbfs(work->ordered,window_frames,4,0);
        portENTER_CRITICAL(&view_lock);memcpy(view_db,db,sizeof(db));view_level=level;++view_sequence;portEXIT_CRITICAL(&view_lock);
        ++views;const uint64_t spent=esp_timer_get_time()-compute;
        total_compute_us+=spent;max_compute_us=std::max(max_compute_us,spent);
    }
    after=audio_ingress_snapshot();
    const int64_t ended=esp_timer_get_time();
    if(mic)esp_codec_dev_close(mic);
    if(speaker)esp_codec_dev_close(speaker);
    // F-0001 T2 telemetry: view rate, compute cost and driver loss while listening.
    auto* e=diagnostic_event("sound_session");cJSON_AddStringToObject(e,"result",ok?"closed":"failed");
    cJSON_AddNumberToObject(e,"duration_ms",(ended-started)/1000);cJSON_AddNumberToObject(e,"blocks",blocks);
    cJSON_AddNumberToObject(e,"views",views);cJSON_AddNumberToObject(e,"max_compute_us",max_compute_us);
    cJSON_AddNumberToObject(e,"mean_compute_us",views?total_compute_us/views:0);
    cJSON_AddNumberToObject(e,"overflows",after.overflows-before.overflows);
    cJSON_AddNumberToObject(e,"overwritten_bytes",after.overwritten_bytes-before.overwritten_bytes);
    cJSON_AddNumberToObject(e,"short_reads",after.short_reads-before.short_reads);
    cJSON_AddNumberToObject(e,"read_errors",after.read_errors-before.read_errors);
    diagnostic_emit(e);
}
