#include "sound.h"
#include "sound_model.h"
#include "sound_analysis.h"
#include "spectrum_display.h"
#include "audio_devices.h"
#include "audio_ingress.h"
#include "diagnostic_events.h"
#include "home.h"
#include "investigation.h"
#include "bsp/m5stack_tab5.h"
#include "esp_random.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <memory>
#include <string>

namespace {
QueueHandle_t media;
std::atomic<bool> stop{true};
lv_obj_t *panel,*chart,*level_label,*level_bar;
lv_chart_series_t *live_series,*peak_series;
// Media owner -> LVGL timer: the latest view, copied under the lock.
portMUX_TYPE view_lock=portMUX_INITIALIZER_UNLOCKED;
float view_db[spectrum_band_count];float view_level=sound::level_floor_db;unsigned view_sequence=0; // view_lock
// LVGL task only.
float peak[spectrum_band_count];unsigned drawn_sequence=0,draws=0;
// Analysis (F-0002): the media owner writes result and strip, then sets analysis_state
// to ready or failed; the LVGL timer reads them only after that.
std::atomic<bool> analysis_requested{false};
enum AnalysisState {Idle,Pending,Ready,TooShort};
std::atomic<int> analysis_state{Idle};
sound::Analysis result;constexpr size_t strip_points=240;float strip[strip_points];size_t strip_count=0;
bool analysis_shown=false; // LVGL task
lv_obj_t *analysis_panel,*analysis_heading,*summary_label,*events_label,*strip_chart,*strip_end,*listen_button;
lv_obj_t *status_label,*explain_button,*explain_label,*home_button;
std::string events_text; // LVGL task: the event list, shown under the agent's reading
// Media owner only: per-second loudest level (sent to the Mac).
constexpr size_t max_seconds=900;float per_second[max_seconds];size_t second_count=0;
std::atomic<bool> explaining{false};
lv_chart_series_t *strip_series,*threshold_series;

void set_chart(lv_chart_series_t* series,const float* db) {
    for(size_t i=0;i<spectrum_band_count;++i)lv_chart_set_value_by_id(chart,series,i,spectrum_chart_value(db[i]));
}
void clear_peak() {
    sound::reset_peak(peak,spectrum_band_count);
    for(size_t i=0;i<spectrum_band_count;++i)lv_chart_set_value_by_id(chart,peak_series,i,LV_CHART_POINT_NONE);
}
void draw(lv_timer_t*) {
    if(lv_obj_has_flag(panel,LV_OBJ_FLAG_HIDDEN))return;
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
    cJSON_AddNumberToObject(e,"draws",draws);diagnostic_emit(e);
}
void reset(lv_event_t*) {clear_peak();lv_chart_refresh(chart);log_control("reset_peak");}
void back(lv_event_t*) {
    stop.store(true);lv_obj_add_flag(panel,LV_OBJ_FLAG_HIDDEN);log_control("back");home_returned("sound");
}
void show_analysis() {
    analysis_shown=true;
    if(analysis_state.load()==TooShort) {
        lv_label_set_text(analysis_heading,"Sound analysis");
        lv_label_set_text(summary_label,"Listen for at least a few seconds, then tap Analysis.");
        lv_obj_remove_state(listen_button,LV_STATE_DISABLED);return;
    }
    const auto& a=result;char when[16],hz[16],line[160];
    std::string summary,events;
    sound::clock_text(a.duration_s,when,sizeof(when));
    snprintf(line,sizeof(line),"Listened %s\n\nBackground  %.0f dB\n",when,a.background_db);summary+=line;
    snprintf(line,sizeof(line),"Loud (10%% of the time)  %+.0f dB\nAverage  %+.0f dB\n",a.loud_db-a.background_db,a.average_db-a.background_db);summary+=line;
    sound::clock_text(a.max_at_s,when,sizeof(when));
    snprintf(line,sizeof(line),"Loudest  %+.0f dB at %s\n\n",a.max_db-a.background_db,when);summary+=line;
    sound::hz_text(a.strongest_background_hz,hz,sizeof(hz));
    snprintf(line,sizeof(line),"Background strongest near %s\n",hz);summary+=line;
    if(!a.tone_count)summary+="Steady tones: none\n";
    for(unsigned i=0;i<a.tone_count;++i) {
        sound::hz_text(a.tones[i].hz,hz,sizeof(hz));
        snprintf(line,sizeof(line),"%s %s (%+.0f dB)\n",i?"             ":"Steady tones:",hz,a.tones[i].above_db);summary+=line;
    }
    if(a.sharp_count) {
        unsigned loudest=0;
        for(unsigned i=1;i<std::min<unsigned>(a.sharp_count,sound::max_sharp);++i)
            if(a.sharp[i].peak_over_db>a.sharp[loudest].peak_over_db)loudest=i;
        sound::clock_text(a.sharp[loudest].at_s,when,sizeof(when));
        snprintf(line,sizeof(line),"Sharp sounds (under 0.3 s): %u, loudest %+.0f dB at %s\n",a.sharp_count,a.sharp[loudest].peak_over_db,when);
        summary+=line;
    } else summary+="Sharp sounds (under 0.3 s): none\n";
    summary+="\n+dB is above the background. Levels are relative, not calibrated.";
    lv_label_set_text(summary_label,summary.c_str());
    if(!a.event_count)events="No loud events: nothing rose 10 dB above the background for 0.3 s.";
    else {
        snprintf(line,sizeof(line),"%u loud event%s (10 dB or more above the background)\n\n",a.event_count,a.event_count==1?"":"s");events+=line;
        for(unsigned i=0;i<std::min<unsigned>(a.event_count,sound::max_events);++i) {
            const auto& e=a.events[i];sound::clock_text(e.start_s,when,sizeof(when));sound::hz_text(e.band_hz,hz,sizeof(hz));
            snprintf(line,sizeof(line),"%u.  %s   %.1f s   %+.0f dB   strongest near %s\n",i+1,when,e.duration_s,e.peak_over_db,hz);events+=line;
        }
        if(a.event_count>sound::max_events){snprintf(line,sizeof(line),"and %u more",a.event_count-unsigned(sound::max_events));events+=line;}
    }
    events_text=events;lv_label_set_text(events_label,events.c_str());
    lv_label_set_text(analysis_heading,"Sound analysis");
    lv_label_set_text(status_label,"Tap Explain to have the agent read this analysis.");
    lv_obj_remove_state(explain_button,LV_STATE_DISABLED);
    // Level over time with the event threshold; y spans background-10 to loudest+3 dB.
    lv_chart_set_point_count(strip_chart,strip_count);
    lv_chart_set_range(strip_chart,LV_CHART_AXIS_PRIMARY_Y,static_cast<int32_t>(std::floor(a.background_db-10)),
                       static_cast<int32_t>(std::ceil(a.max_db+3)));
    for(size_t i=0;i<strip_count;++i) {
        lv_chart_set_value_by_id(strip_chart,strip_series,i,static_cast<int32_t>(std::lround(strip[i])));
        lv_chart_set_value_by_id(strip_chart,threshold_series,i,static_cast<int32_t>(std::lround(a.threshold_db)));
    }
    lv_chart_refresh(strip_chart);
    sound::clock_text(a.duration_s,when,sizeof(when));lv_label_set_text(strip_end,when);
    lv_obj_remove_flag(strip_chart,LV_OBJ_FLAG_HIDDEN);lv_obj_remove_state(listen_button,LV_STATE_DISABLED);
}
void draw_analysis(lv_timer_t*) {
    if(analysis_shown || lv_obj_has_flag(analysis_panel,LV_OBJ_FLAG_HIDDEN))return;
    const int state=analysis_state.load();
    if(state==Ready || state==TooShort)show_analysis();
}
void analysis_clicked(lv_event_t*) {
    analysis_shown=false;analysis_state.store(Pending);analysis_requested.store(true);stop.store(true);
    lv_label_set_text(analysis_heading,"Analyzing...");lv_label_set_text(summary_label,"");lv_label_set_text(events_label,"");
    lv_obj_add_flag(strip_chart,LV_OBJ_FLAG_HIDDEN);lv_label_set_text(strip_end,"");
    lv_obj_add_state(listen_button,LV_STATE_DISABLED); // until the listening loop has ended
    lv_obj_add_state(explain_button,LV_STATE_DISABLED);
    lv_label_set_text(status_label,"");lv_label_set_text(explain_label,"Explain");
    lv_obj_remove_flag(analysis_panel,LV_OBJ_FLAG_HIDDEN);lv_obj_move_foreground(analysis_panel);
    log_control("analysis");
}
void listen_again(lv_event_t*) {
    investigation_stop_speech();lv_obj_add_flag(analysis_panel,LV_OBJ_FLAG_HIDDEN);log_control("listen_again");sound_ui_open();
}
void send_media(uint8_t command) {
    if(xQueueSend(media,&command,0)!=pdTRUE) {
        auto* e=diagnostic_event("sound_session");cJSON_AddStringToObject(e,"result","queue_full");
        cJSON_AddNumberToObject(e,"command",command);diagnostic_emit(e);
    }
}
// Explain: while the agent answers or speaks, the button stops the voice.
void explain_clicked(lv_event_t*) {
    if(explaining.load()){investigation_stop_speech();log_control("explain_stop_voice");return;}
    explaining.store(true);lv_label_set_text(explain_label,"Stop voice");
    lv_obj_add_state(listen_button,LV_STATE_DISABLED);
    log_control("explain");send_media(sound_explain_command);
}
void analysis_home(lv_event_t*) {
    investigation_stop_speech();
    lv_obj_add_flag(analysis_panel,LV_OBJ_FLAG_HIDDEN);lv_obj_add_flag(panel,LV_OBJ_FLAG_HIDDEN);
    log_control("analysis_home");home_returned("analysis");
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
    button(panel,"Analysis",690,analysis_clicked);
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

    analysis_panel=lv_obj_create(screen);lv_obj_remove_style_all(analysis_panel);
    lv_obj_set_size(analysis_panel,1280,720);lv_obj_set_pos(analysis_panel,0,0);
    lv_obj_set_style_bg_color(analysis_panel,lv_color_hex(0x101418),0);lv_obj_set_style_bg_opa(analysis_panel,LV_OPA_COVER,0);
    lv_obj_remove_flag(analysis_panel,LV_OBJ_FLAG_SCROLLABLE);
    analysis_heading=text(analysis_panel,"Sound analysis",24,20,&lv_font_montserrat_40,0xffffff);
    explain_label=button(analysis_panel,"Explain",690,explain_clicked);explain_button=lv_obj_get_parent(explain_label);
    lv_obj_add_state(explain_button,LV_STATE_DISABLED);
    status_label=text(analysis_panel,"",24,82,&lv_font_montserrat_20,0x4fc3f7);
    lv_obj_set_width(status_label,1232);lv_label_set_long_mode(status_label,LV_LABEL_LONG_DOT);
    listen_button=lv_obj_get_parent(button(analysis_panel,"Listen again",886,listen_again));
    button(analysis_panel,"Home",1082,analysis_home);
    auto* column=lv_obj_create(analysis_panel);lv_obj_set_pos(column,24,114);lv_obj_set_size(column,470,586);
    lv_obj_set_style_bg_color(column,lv_color_hex(0x161c21),0);lv_obj_set_style_border_width(column,0,0);
    lv_obj_set_style_pad_all(column,20,0);lv_obj_set_scroll_dir(column,LV_DIR_VER);
    summary_label=text(column,"",0,0,&lv_font_montserrat_24,0xe0e0e0);
    lv_obj_set_width(summary_label,lv_pct(100));lv_label_set_long_mode(summary_label,LV_LABEL_LONG_WRAP);
    lv_obj_set_style_text_line_space(summary_label,6,0);
    strip_chart=lv_chart_create(analysis_panel);lv_obj_set_pos(strip_chart,520,114);lv_obj_set_size(strip_chart,736,222);
    lv_chart_set_type(strip_chart,LV_CHART_TYPE_LINE);lv_chart_set_div_line_count(strip_chart,4,0);
    lv_obj_set_style_pad_all(strip_chart,0,0);lv_obj_set_style_bg_color(strip_chart,lv_color_hex(0x000000),0);
    lv_obj_set_style_border_color(strip_chart,lv_color_hex(0x37474f),0);
    lv_obj_set_style_line_color(strip_chart,lv_color_hex(0x263238),LV_PART_MAIN);
    lv_obj_set_style_line_width(strip_chart,2,LV_PART_ITEMS);lv_obj_set_style_size(strip_chart,0,0,LV_PART_INDICATOR);
    threshold_series=lv_chart_add_series(strip_chart,lv_color_hex(0xffb74d),LV_CHART_AXIS_PRIMARY_Y);
    strip_series=lv_chart_add_series(strip_chart,lv_color_hex(0x66bb6a),LV_CHART_AXIS_PRIMARY_Y);
    text(analysis_panel,"0:00",520,342,&lv_font_montserrat_20,0x90a4ae);
    strip_end=text(analysis_panel,"",1196,342,&lv_font_montserrat_20,0x90a4ae);
    text(analysis_panel,"Level",700,342,&lv_font_montserrat_20,0x66bb6a);
    text(analysis_panel,"Event threshold",780,342,&lv_font_montserrat_20,0xffb74d);
    auto* list=lv_obj_create(analysis_panel);lv_obj_set_pos(list,520,378);lv_obj_set_size(list,736,322);
    lv_obj_set_style_bg_color(list,lv_color_hex(0x161c21),0);lv_obj_set_style_border_width(list,0,0);
    lv_obj_set_style_pad_all(list,20,0);lv_obj_set_scroll_dir(list,LV_DIR_VER);
    events_label=text(list,"",0,0,&lv_font_montserrat_22,0xe0e0e0);
    lv_obj_set_width(events_label,lv_pct(100));lv_label_set_long_mode(events_label,LV_LABEL_LONG_WRAP);
    lv_obj_set_style_text_line_space(events_label,6,0);
    lv_timer_create(draw_analysis,100,nullptr);
    lv_obj_add_flag(analysis_panel,LV_OBJ_FLAG_HIDDEN);
}

void sound_ui_open() {
    draws=0;
    clear_peak();lv_label_set_text(level_label,"-- dB");lv_bar_set_value(level_bar,-100,LV_ANIM_OFF);
    for(size_t i=0;i<spectrum_band_count;++i)lv_chart_set_value_by_id(chart,live_series,i,LV_CHART_POINT_NONE);
    lv_obj_remove_flag(panel,LV_OBJ_FLAG_HIDDEN);lv_obj_move_foreground(panel);
    stop.store(false);
    const uint8_t command=sound_media_command;
    if(xQueueSend(media,&command,0)!=pdTRUE) {
        auto* e=diagnostic_event("sound_session");cJSON_AddStringToObject(e,"result","queue_full");diagnostic_emit(e);
    }
}

namespace {
// Media owner, after listening stops. F-0002 T4 telemetry: every number shown, plus
// the loudest level in each second, to compare with what the user heard.
void analyze_session(const sound::Frame* frames,size_t n,float period_s,bool truncated) {
    const int64_t started=esp_timer_get_time();
    std::unique_ptr<float,decltype(&free)> scratch(static_cast<float*>(
        heap_caps_malloc((n?n:1)*sizeof(float),MALLOC_CAP_SPIRAM)),free);
    float band_hz[spectrum_band_count];
    for(size_t b=0;b<spectrum_band_count;++b)band_hz[b]=std::sqrt(spectrum_band_edge_hz(b)*spectrum_band_edge_hz(b+1));
    const bool ok=frames && scratch && sound::analyze(frames,n,period_s,band_hz,scratch.get(),result);
    auto* e=diagnostic_event("sound_analysis");
    cJSON_AddStringToObject(e,"result",ok?"ready":"too_short");cJSON_AddNumberToObject(e,"frames",n);
    cJSON_AddNumberToObject(e,"frame_period_s",period_s);cJSON_AddBoolToObject(e,"truncated",truncated);
    if(ok) {
        for(size_t i=0;i<n;++i)scratch.get()[i]=frames[i].level_db;
        strip_count=std::min(strip_points,n);sound::bucket_max(scratch.get(),n,strip,strip_count);
        const auto& a=result;
        cJSON_AddNumberToObject(e,"duration_s",a.duration_s);cJSON_AddNumberToObject(e,"background_db",a.background_db);
        cJSON_AddNumberToObject(e,"loud_db",a.loud_db);cJSON_AddNumberToObject(e,"average_db",a.average_db);
        cJSON_AddNumberToObject(e,"max_db",a.max_db);cJSON_AddNumberToObject(e,"max_at_s",a.max_at_s);
        cJSON_AddNumberToObject(e,"threshold_db",a.threshold_db);
        cJSON_AddNumberToObject(e,"strongest_background_hz",a.strongest_background_hz);
        cJSON_AddNumberToObject(e,"event_count",a.event_count);
        auto* events=cJSON_AddArrayToObject(e,"events");
        for(unsigned i=0;i<std::min<unsigned>(a.event_count,sound::max_events);++i) {
            const auto& v=a.events[i];auto* o=cJSON_CreateObject();
            cJSON_AddNumberToObject(o,"start_s",v.start_s);cJSON_AddNumberToObject(o,"duration_s",v.duration_s);
            cJSON_AddNumberToObject(o,"peak_over_db",v.peak_over_db);cJSON_AddNumberToObject(o,"band_hz",v.band_hz);
            cJSON_AddNumberToObject(o,"band_rise_db",v.band_rise_db);cJSON_AddItemToArray(events,o);
        }
        auto* tones=cJSON_AddArrayToObject(e,"tones");
        for(unsigned i=0;i<a.tone_count;++i) {
            auto* o=cJSON_CreateObject();cJSON_AddNumberToObject(o,"hz",a.tones[i].hz);
            cJSON_AddNumberToObject(o,"above_db",a.tones[i].above_db);cJSON_AddItemToArray(tones,o);
        }
        auto* sharp=cJSON_AddArrayToObject(e,"sharp");cJSON_AddNumberToObject(e,"sharp_count",a.sharp_count);
        for(unsigned i=0;i<std::min<unsigned>(a.sharp_count,sound::max_sharp);++i) {
            auto* o=cJSON_CreateObject();cJSON_AddNumberToObject(o,"at_s",a.sharp[i].at_s);
            cJSON_AddNumberToObject(o,"peak_over_db",a.sharp[i].peak_over_db);cJSON_AddItemToArray(sharp,o);
        }
        second_count=std::min({max_seconds,n,std::max<size_t>(1,static_cast<size_t>(std::lround(a.duration_s)))});
        sound::bucket_max(scratch.get(),n,per_second,second_count);
        auto* levels=cJSON_AddArrayToObject(e,"level_max_1s");
        for(size_t i=0;i<second_count;++i)cJSON_AddItemToArray(levels,cJSON_CreateNumber(std::round(per_second[i]*10)/10));
    }
    cJSON_AddNumberToObject(e,"compute_us",esp_timer_get_time()-started);diagnostic_emit(e);
    analysis_state.store(ok?Ready:TooShort);
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
    // F-0002: pairs of views become 85 ms frames, up to 10 minutes (about 1.4 MB).
    constexpr size_t max_frames=7200;constexpr float frame_period_s=4.0f*block_frames/48000;
    std::unique_ptr<sound::Frame,decltype(&free)> record(static_cast<sound::Frame*>(
        heap_caps_calloc(max_frames,sizeof(sound::Frame),MALLOC_CAP_SPIRAM)),free);
    size_t recorded=0;bool truncated=false;unsigned paired=0;double pair_level=0,pair_bands[spectrum_band_count]{};
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
        if(record) {
            pair_level+=sound::power(level);for(size_t b=0;b<spectrum_band_count;++b)pair_bands[b]+=sound::power(db[b]);
            if(++paired==2) {
                if(recorded<max_frames) {
                    auto& f=record.get()[recorded++];f.level_db=sound::decibels(pair_level/2);
                    for(size_t b=0;b<spectrum_band_count;++b)f.band_db[b]=sound::decibels(pair_bands[b]/2);
                } else truncated=true;
                paired=0;pair_level=0;for(auto& p:pair_bands)p=0;
            }
        }
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
    cJSON_AddNumberToObject(e,"recorded_frames",recorded);cJSON_AddBoolToObject(e,"record_allocated",record!=nullptr);
    diagnostic_emit(e);
    if(analysis_requested.exchange(false))analyze_session(record.get(),recorded,frame_period_s,truncated);
}

namespace {
cJSON* rounded(double value) {return cJSON_CreateNumber(std::round(value*10)/10);}
// The summary the Mac checks (tools/sound_explain.py FIELDS); levels in device dBFS.
cJSON* analysis_summary() {
    const auto& a=result;auto* o=cJSON_CreateObject();
    const std::pair<const char*,float> top[]={{"duration_s",a.duration_s},{"background_db",a.background_db},
        {"loud_db",a.loud_db},{"average_db",a.average_db},{"max_db",a.max_db},{"max_at_s",a.max_at_s},
        {"threshold_db",a.threshold_db},{"strongest_background_hz",a.strongest_background_hz}};
    for(const auto& [key,value]:top)cJSON_AddItemToObject(o,key,rounded(value));
    cJSON_AddNumberToObject(o,"event_count",a.event_count);cJSON_AddNumberToObject(o,"sharp_count",a.sharp_count);
    auto* events=cJSON_AddArrayToObject(o,"events");
    for(unsigned i=0;i<std::min<unsigned>(a.event_count,sound::max_events);++i) {
        const auto& v=a.events[i];auto* e=cJSON_CreateObject();
        cJSON_AddItemToObject(e,"start_s",rounded(v.start_s));cJSON_AddItemToObject(e,"duration_s",rounded(v.duration_s));
        cJSON_AddItemToObject(e,"peak_over_db",rounded(v.peak_over_db));cJSON_AddItemToObject(e,"band_hz",rounded(v.band_hz));
        cJSON_AddItemToObject(e,"band_rise_db",rounded(v.band_rise_db));cJSON_AddItemToArray(events,e);
    }
    auto* tones=cJSON_AddArrayToObject(o,"tones");
    for(unsigned i=0;i<a.tone_count;++i) {
        auto* t=cJSON_CreateObject();cJSON_AddItemToObject(t,"tone_hz",rounded(a.tones[i].hz));
        cJSON_AddItemToObject(t,"above_db",rounded(a.tones[i].above_db));cJSON_AddItemToArray(tones,t);
    }
    auto* sharp=cJSON_AddArrayToObject(o,"sharp");
    for(unsigned i=0;i<std::min<unsigned>(a.sharp_count,sound::max_sharp);++i) {
        auto* t=cJSON_CreateObject();cJSON_AddItemToObject(t,"at_s",rounded(a.sharp[i].at_s));
        cJSON_AddItemToObject(t,"peak_over_db",rounded(a.sharp[i].peak_over_db));cJSON_AddItemToArray(sharp,t);
    }
    auto* levels=cJSON_AddArrayToObject(o,"level_max_1s");
    for(size_t i=0;i<second_count;++i)cJSON_AddItemToArray(levels,rounded(per_second[i]));
    return o;
}
void new_session(char* out,size_t size) {
    snprintf(out,size,"sa-%08lx%08lx%08lx%08lx",static_cast<unsigned long>(esp_random()),static_cast<unsigned long>(esp_random()),
             static_cast<unsigned long>(esp_random()),static_cast<unsigned long>(esp_random()));
}
// Media task -> screen; takes the display lock for each update.
void explain_progress(const char* stage,const char*,const char* text) {
    if(!bsp_display_lock(1000))return;
    if(stage)lv_label_set_text(status_label,stage);
    if(text) {
        const std::string shown="Agent: "+std::string(text)+"\n\n"+events_text;
        lv_label_set_text(events_label,shown.c_str());lv_obj_scroll_to_y(lv_obj_get_parent(events_label),0,LV_ANIM_OFF);
        lv_label_set_text(status_label,"The agent's reading is below. Stop voice ends the speech.");
    }
    bsp_display_unlock();
}
void restore_buttons(const char* status) {
    if(!bsp_display_lock(1000))return;
    lv_label_set_text(status_label,status);lv_label_set_text(explain_label,"Explain");
    for(auto* b:{explain_button,listen_button})lv_obj_remove_state(b,LV_STATE_DISABLED);
    bsp_display_unlock();
}
}

void sound_explain(const char* boot) {
    // A fresh session each time, so Explain can be retried.
    char session[40];new_session(session,sizeof(session));
    SoundExplainHooks hooks{explain_progress};
    SoundExplainResult out;
    const bool ok=analysis_state.load()==Ready &&
        investigation_explain_sound(boot,session,nullptr,analysis_summary(),hooks,out);
    explaining.store(false);
    restore_buttons(ok?"Tap Explain to ask again.":out.error.empty()?"Nothing to explain yet.":out.error.c_str());
}
