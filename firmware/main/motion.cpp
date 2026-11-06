#include "motion.h"
#include "motion_analysis.h"
#include "sound_analysis.h"
#include "diagnostic_events.h"
#include "home.h"
#include "imu_checked.h"
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
lv_obj_t *panel,*trace_chart,*tilt_chart,*tilt_label,*peak_label,*scale_top,*scale_bottom;
lv_chart_series_t *trace_series,*tilt_series;
// Media owner -> LVGL timer: 20 points a second, each the 10 ms sample that moved most
// from 1 g in its 50 ms, with the tilt of their mean.
struct Point {float change_g,tilt_deg;};
constexpr size_t point_ring=64;
portMUX_TYPE view_lock=portMUX_INITIALIZER_UNLOCKED;
Point points[point_ring];unsigned point_total=0; // view_lock
// LVGL task only.
constexpr size_t trace_points=120; // 6 s
float recent[trace_points];size_t recent_next=0;
unsigned drawn_total=0,draws=0;float peak=0,shown_span=0;bool have_point=false;
// Analysis: the media owner writes result and strip, then sets analysis_state; the
// LVGL timer reads them only after that.
std::atomic<bool> analysis_requested{false};
enum AnalysisState {Idle,Pending,Ready,TooShort};
std::atomic<int> analysis_state{Idle};
motion::Analysis result;constexpr size_t strip_points=240;float strip[strip_points];size_t strip_count=0;
bool analysis_shown=false; // LVGL task
lv_obj_t *analysis_panel,*analysis_heading,*summary_label,*events_label,*strip_chart,*strip_end,*again_button;
lv_obj_t *status_label,*explain_button,*explain_label;
lv_chart_series_t *strip_series,*threshold_series;
std::string events_text; // LVGL task: the event list, shown under the agent's reading
std::atomic<bool> explaining{false};

int32_t milli(float g) {return static_cast<int32_t>(std::lround(g*1000));}
void set_span(float span) {
    shown_span=span;lv_chart_set_range(trace_chart,LV_CHART_AXIS_PRIMARY_Y,-milli(span),milli(span));
    char text[24],value[16];motion::g_text(span,value,sizeof(value));
    snprintf(text,sizeof(text),"+%s",value);lv_label_set_text(scale_top,text);
    snprintf(text,sizeof(text),"-%s",value);lv_label_set_text(scale_bottom,text);
}
void show_peak() {
    char text[32],value[16];motion::g_text(peak,value,sizeof(value));
    snprintf(text,sizeof(text),"Peak %s",value);lv_label_set_text(peak_label,text);
}
void draw(lv_timer_t*) {
    if(lv_obj_has_flag(panel,LV_OBJ_FLAG_HIDDEN))return;
    Point fresh[point_ring];unsigned total,count;
    portENTER_CRITICAL(&view_lock);
    total=point_total;count=std::min<unsigned>(total-drawn_total,point_ring);
    for(unsigned i=0;i<count;++i)fresh[i]=points[(total-count+i)%point_ring];
    portEXIT_CRITICAL(&view_lock);
    if(!count)return;
    drawn_total=total;++draws;have_point=true;
    for(unsigned i=0;i<count;++i) {
        const auto& p=fresh[i];
        lv_chart_set_next_value(trace_chart,trace_series,milli(p.change_g));
        lv_chart_set_next_value(tilt_chart,tilt_series,static_cast<int32_t>(std::lround(p.tilt_deg)));
        recent[recent_next]=std::fabs(p.change_g);recent_next=(recent_next+1)%trace_points;
        peak=std::max(peak,std::fabs(p.change_g));
    }
    const float largest=*std::max_element(recent,recent+trace_points);
    float span=4;
    for(float s:{0.05f,0.1f,0.2f,0.5f,1.0f,2.0f})if(largest<=0.9f*s){span=s;break;}
    if(span!=shown_span)set_span(span);
    char text[24];snprintf(text,sizeof(text),"Tilt %d\xc2\xb0",static_cast<int>(std::lround(fresh[count-1].tilt_deg)));
    lv_label_set_text(tilt_label,text);show_peak();
}
void log_control(const char* control) {
    auto* e=diagnostic_event("motion_control");cJSON_AddStringToObject(e,"control",control);
    cJSON_AddNumberToObject(e,"draws",draws);diagnostic_emit(e);
}
void reset(lv_event_t*) {peak=0;if(have_point)show_peak();log_control("reset_peak");}
void back(lv_event_t*) {
    stop.store(true);lv_obj_add_flag(panel,LV_OBJ_FLAG_HIDDEN);log_control("back");home_returned("motion");
}
void duration_text(float seconds,char* out,size_t size) {snprintf(out,size,seconds<1?"%.2f s":"%.1f s",seconds);}
void show_analysis() {
    analysis_shown=true;
    lv_label_set_text(analysis_heading,"Motion analysis");
    if(analysis_state.load()==TooShort) {
        lv_label_set_text(summary_label,"Measure for at least a few seconds, then tap Analysis.");
        lv_obj_remove_state(again_button,LV_STATE_DISABLED);return;
    }
    const auto& a=result;char when[16],g[16],g2[16],line[200];
    std::string summary,events;
    sound::clock_text(a.duration_s,when,sizeof(when));
    snprintf(line,sizeof(line),"Measured %s\n\nSteadiness: %s\n",when,motion::steadiness_name(a.steadiness));summary+=line;
    snprintf(line,sizeof(line),"Held still %u s, in hand %u s, moving %u s\n",a.steadiness_s[motion::HeldStill],
             a.steadiness_s[motion::InHand],a.steadiness_s[motion::Moving]);summary+=line;
    sound::clock_text(a.steadiest_at_s,when,sizeof(when));motion::g_text(a.steadiest_g,g,sizeof(g));
    snprintf(line,sizeof(line),"Steadiest second %s (%s)\n",when,g);summary+=line;
    sound::clock_text(a.shakiest_at_s,when,sizeof(when));motion::g_text(a.shakiest_g,g,sizeof(g));
    snprintf(line,sizeof(line),"Shakiest second %s (%s)\n\n",when,g);summary+=line;
    sound::clock_text(a.peak_at_s,when,sizeof(when));motion::g_text(a.peak_g,g,sizeof(g));
    snprintf(line,sizeof(line),"Biggest jolt %s at %s\n",g,when);summary+=line;
    snprintf(line,sizeof(line),"Tilt %.0f\xc2\xb0 to %.0f\xc2\xb0, mostly %s\n",a.tilt_min_deg,a.tilt_max_deg,
             motion::orientation_name(a.orientation));summary+=line;
    snprintf(line,sizeof(line),"Flat %u s, tilted %u s, upright %u s\n\n",a.orientation_s[motion::Flat],
             a.orientation_s[motion::Tilted],a.orientation_s[motion::Upright]);summary+=line;
    if(a.vibration) {
        motion::g_text(a.vibration_g,g,sizeof(g));
        snprintf(line,sizeof(line),"Vibration %.1f Hz, %s (resting %.0f s)\n",a.vibration_hz,g,a.rest_s);
    } else if(a.rest_s>=motion::min_rest_s)
        snprintf(line,sizeof(line),"Vibration: nothing stood out (resting %.0f s)\n",a.rest_s);
    else snprintf(line,sizeof(line),"Vibration: not measured; set the device down for %.0f s or more\n",motion::min_rest_s);
    summary+=line;
    summary+="\nMovement is the spread of the acceleration in each second; jolts are changes from gravity. "
             "The sensor measures the device itself and is not calibrated.";
    lv_label_set_text(summary_label,summary.c_str());
    motion::g_text(motion::event_rise_g,g,sizeof(g));
    if(!a.event_count) {
        snprintf(line,sizeof(line),"No jolts: nothing rose %s above the quiet level.",g);events=line;
    } else {
        motion::g_text(a.quiet_g,g2,sizeof(g2));
        snprintf(line,sizeof(line),"%u jolt%s (%s or more above the quiet level of %s)\n\n",a.event_count,
                 a.event_count==1?"":"s",g,g2);events+=line;
        for(unsigned i=0;i<std::min<unsigned>(a.event_count,motion::max_events);++i) {
            const auto& e=a.events[i];char length[16];
            sound::clock_text(e.start_s,when,sizeof(when));duration_text(e.duration_s,length,sizeof(length));
            motion::g_text(e.peak_g,g,sizeof(g));
            snprintf(line,sizeof(line),"%u.  %s   %s   %s\n",i+1,when,length,g);events+=line;
        }
        if(a.event_count>motion::max_events){snprintf(line,sizeof(line),"and %u more",a.event_count-unsigned(motion::max_events));events+=line;}
    }
    events_text=events;lv_label_set_text(events_label,events.c_str());
    lv_label_set_text(status_label,"Tap Explain to have the agent read this analysis.");
    lv_obj_remove_state(explain_button,LV_STATE_DISABLED);
    // Change from gravity over time with the jolt threshold, in mg.
    lv_chart_set_point_count(strip_chart,strip_count);
    lv_chart_set_range(strip_chart,LV_CHART_AXIS_PRIMARY_Y,0,std::max(milli(a.peak_g*1.1f),milli(a.threshold_g*1.5f)));
    for(size_t i=0;i<strip_count;++i) {
        lv_chart_set_value_by_id(strip_chart,strip_series,i,milli(strip[i]));
        lv_chart_set_value_by_id(strip_chart,threshold_series,i,milli(a.threshold_g));
    }
    lv_chart_refresh(strip_chart);
    sound::clock_text(a.duration_s,when,sizeof(when));lv_label_set_text(strip_end,when);
    lv_obj_remove_flag(strip_chart,LV_OBJ_FLAG_HIDDEN);lv_obj_remove_state(again_button,LV_STATE_DISABLED);
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
    lv_obj_add_state(again_button,LV_STATE_DISABLED); // until the sampling loop has ended
    lv_obj_add_state(explain_button,LV_STATE_DISABLED);
    lv_label_set_text(status_label,"");lv_label_set_text(explain_label,"Explain");
    lv_obj_remove_flag(analysis_panel,LV_OBJ_FLAG_HIDDEN);lv_obj_move_foreground(analysis_panel);
    log_control("analysis");
}
void measure_again(lv_event_t*) {
    investigation_stop_speech();lv_obj_add_flag(analysis_panel,LV_OBJ_FLAG_HIDDEN);log_control("measure_again");motion_ui_open();
}
void send_media(uint8_t command) {
    if(xQueueSend(media,&command,0)!=pdTRUE) {
        auto* e=diagnostic_event("motion_session");cJSON_AddStringToObject(e,"result","queue_full");
        cJSON_AddNumberToObject(e,"command",command);diagnostic_emit(e);
    }
}
// Explain: while the agent answers or speaks, the button stops the voice.
void explain_clicked(lv_event_t*) {
    if(explaining.load()){investigation_stop_speech();log_control("explain_stop_voice");return;}
    explaining.store(true);lv_label_set_text(explain_label,"Stop voice");
    lv_obj_add_state(again_button,LV_STATE_DISABLED);
    log_control("explain");send_media(motion_explain_command);
}
void analysis_home(lv_event_t*) {
    investigation_stop_speech();
    lv_obj_add_flag(analysis_panel,LV_OBJ_FLAG_HIDDEN);lv_obj_add_flag(panel,LV_OBJ_FLAG_HIDDEN);
    log_control("analysis_home");home_returned("motion_analysis");
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
lv_obj_t* chart(lv_obj_t* parent,int x,int y,int w,int h) {
    auto* c=lv_chart_create(parent);lv_obj_set_pos(c,x,y);lv_obj_set_size(c,w,h);
    lv_chart_set_type(c,LV_CHART_TYPE_LINE);lv_chart_set_div_line_count(c,5,0);
    lv_obj_set_style_pad_all(c,0,0);lv_obj_set_style_bg_color(c,lv_color_hex(0x000000),0);
    lv_obj_set_style_border_color(c,lv_color_hex(0x37474f),0);
    lv_obj_set_style_line_color(c,lv_color_hex(0x263238),LV_PART_MAIN);
    lv_obj_set_style_line_width(c,3,LV_PART_ITEMS);lv_obj_set_style_size(c,0,0,LV_PART_INDICATOR);
    return c;
}
lv_obj_t* panel_base(lv_obj_t* screen) {
    auto* p=lv_obj_create(screen);lv_obj_remove_style_all(p);lv_obj_set_size(p,1280,720);lv_obj_set_pos(p,0,0);
    lv_obj_set_style_bg_color(p,lv_color_hex(0x101418),0);lv_obj_set_style_bg_opa(p,LV_OPA_COVER,0);
    lv_obj_remove_flag(p,LV_OBJ_FLAG_SCROLLABLE);return p;
}
lv_obj_t* scroll_box(lv_obj_t* parent,int x,int y,int w,int h,const lv_font_t* font) {
    auto* box=lv_obj_create(parent);lv_obj_set_pos(box,x,y);lv_obj_set_size(box,w,h);
    lv_obj_set_style_bg_color(box,lv_color_hex(0x161c21),0);lv_obj_set_style_border_width(box,0,0);
    lv_obj_set_style_pad_all(box,20,0);lv_obj_set_scroll_dir(box,LV_DIR_VER);
    auto* l=text(box,"",0,0,font,0xe0e0e0);
    lv_obj_set_width(l,lv_pct(100));lv_label_set_long_mode(l,LV_LABEL_LONG_WRAP);lv_obj_set_style_text_line_space(l,6,0);
    return l;
}
}

void motion_ui_init(lv_obj_t* screen,QueueHandle_t media_commands) {
    media=media_commands;
    panel=panel_base(screen);
    text(panel,"Motion",24,20,&lv_font_montserrat_40,0xffffff);
    tilt_label=text(panel,"Tilt --",210,26,&lv_font_montserrat_32,0x4fc3f7);
    peak_label=text(panel,"Peak --",410,26,&lv_font_montserrat_32,0xffb74d);
    button(panel,"Analysis",690,analysis_clicked);
    button(panel,"Reset peak",886,reset);
    button(panel,"Home",1082,back);

    constexpr int chart_x=130,chart_w=1120,trace_y=110,trace_h=300,tilt_y=470,tilt_h=180;
    trace_chart=chart(panel,chart_x,trace_y,chart_w,trace_h);
    lv_chart_set_point_count(trace_chart,trace_points);lv_chart_set_update_mode(trace_chart,LV_CHART_UPDATE_MODE_SHIFT);
    trace_series=lv_chart_add_series(trace_chart,lv_color_hex(0x66bb6a),LV_CHART_AXIS_PRIMARY_Y);
    scale_top=text(panel,"",20,trace_y-4,&lv_font_montserrat_22,0x90a4ae);
    text(panel,"0",20,trace_y+trace_h/2-12,&lv_font_montserrat_22,0x90a4ae);
    scale_bottom=text(panel,"",20,trace_y+trace_h-24,&lv_font_montserrat_22,0x90a4ae);
    text(panel,"Acceleration minus gravity (green), last 6 s",chart_x,trace_y+trace_h+10,&lv_font_montserrat_22,0x66bb6a);
    tilt_chart=chart(panel,chart_x,tilt_y,chart_w,tilt_h);lv_chart_set_div_line_count(tilt_chart,3,0);
    lv_chart_set_point_count(tilt_chart,trace_points);lv_chart_set_update_mode(tilt_chart,LV_CHART_UPDATE_MODE_SHIFT);
    lv_chart_set_range(tilt_chart,LV_CHART_AXIS_PRIMARY_Y,0,90);
    tilt_series=lv_chart_add_series(tilt_chart,lv_color_hex(0x4fc3f7),LV_CHART_AXIS_PRIMARY_Y);
    text(panel,"90\xc2\xb0",20,tilt_y-4,&lv_font_montserrat_22,0x90a4ae);
    text(panel,"45\xc2\xb0",20,tilt_y+tilt_h/2-12,&lv_font_montserrat_22,0x90a4ae);
    text(panel,"0\xc2\xb0",20,tilt_y+tilt_h-24,&lv_font_montserrat_22,0x90a4ae);
    text(panel,"Tilt from lying flat (blue): 0\xc2\xb0 flat, 90\xc2\xb0 standing on an edge",chart_x,tilt_y+tilt_h+10,
         &lv_font_montserrat_22,0x4fc3f7);
    lv_timer_create(draw,50,nullptr);
    lv_obj_add_flag(panel,LV_OBJ_FLAG_HIDDEN);

    analysis_panel=panel_base(screen);
    analysis_heading=text(analysis_panel,"Motion analysis",24,20,&lv_font_montserrat_40,0xffffff);
    explain_label=button(analysis_panel,"Explain",690,explain_clicked);explain_button=lv_obj_get_parent(explain_label);
    lv_obj_add_state(explain_button,LV_STATE_DISABLED);
    status_label=text(analysis_panel,"",24,82,&lv_font_montserrat_20,0x4fc3f7);
    lv_obj_set_width(status_label,1232);lv_label_set_long_mode(status_label,LV_LABEL_LONG_DOT);
    again_button=lv_obj_get_parent(button(analysis_panel,"Measure again",886,measure_again));
    button(analysis_panel,"Home",1082,analysis_home);
    summary_label=scroll_box(analysis_panel,24,114,470,586,&lv_font_montserrat_24);
    strip_chart=chart(analysis_panel,520,114,736,222);lv_chart_set_div_line_count(strip_chart,4,0);
    lv_obj_set_style_line_width(strip_chart,2,LV_PART_ITEMS);
    threshold_series=lv_chart_add_series(strip_chart,lv_color_hex(0xffb74d),LV_CHART_AXIS_PRIMARY_Y);
    strip_series=lv_chart_add_series(strip_chart,lv_color_hex(0x66bb6a),LV_CHART_AXIS_PRIMARY_Y);
    text(analysis_panel,"0:00",520,342,&lv_font_montserrat_20,0x90a4ae);
    strip_end=text(analysis_panel,"",1196,342,&lv_font_montserrat_20,0x90a4ae);
    text(analysis_panel,"Change from gravity",640,342,&lv_font_montserrat_20,0x66bb6a);
    text(analysis_panel,"Jolt threshold",860,342,&lv_font_montserrat_20,0xffb74d);
    events_label=scroll_box(analysis_panel,520,378,736,322,&lv_font_montserrat_22);
    lv_timer_create(draw_analysis,100,nullptr);
    lv_obj_add_flag(analysis_panel,LV_OBJ_FLAG_HIDDEN);
}

void motion_ui_open() {
    draws=0;peak=0;have_point=false;shown_span=0;recent_next=0;
    for(auto& r:recent)r=0;
    lv_label_set_text(tilt_label,"Tilt --");lv_label_set_text(peak_label,"Peak --");set_span(0.05f);
    lv_chart_set_all_value(trace_chart,trace_series,LV_CHART_POINT_NONE);
    lv_chart_set_all_value(tilt_chart,tilt_series,LV_CHART_POINT_NONE);
    portENTER_CRITICAL(&view_lock);drawn_total=point_total;portEXIT_CRITICAL(&view_lock);
    lv_obj_remove_flag(panel,LV_OBJ_FLAG_HIDDEN);lv_obj_move_foreground(panel);
    stop.store(false);send_media(motion_media_command);
}

namespace {
// Media owner, after sampling stops.
cJSON* analysis_summary();
void analyze_session(const motion::Sample* samples,size_t n) {
    const int64_t started=esp_timer_get_time();
    std::unique_ptr<float,decltype(&free)> scratch(static_cast<float*>(
        heap_caps_malloc((n?n:1)*sizeof(float),MALLOC_CAP_SPIRAM)),free);
    std::unique_ptr<motion::Workspace,decltype(&free)> workspace(static_cast<motion::Workspace*>(
        heap_caps_malloc(sizeof(motion::Workspace),MALLOC_CAP_SPIRAM)),free);
    const bool ok=samples && scratch && workspace && motion::analyze(samples,n,scratch.get(),*workspace,result);
    const int64_t compute_us=esp_timer_get_time()-started;
    if(ok) {
        for(size_t i=0;i<n;++i)scratch.get()[i]=std::fabs(motion::magnitude_g(samples[i])-result.gravity_g);
        strip_count=std::min(strip_points,n);sound::bucket_max(scratch.get(),n,strip,strip_count);
    }
    auto* e=diagnostic_event("motion_analysis");
    cJSON_AddStringToObject(e,"result",ok?"ready":"too_short");cJSON_AddNumberToObject(e,"samples",n);
    cJSON_AddNumberToObject(e,"compute_us",compute_us);
    if(ok)cJSON_AddItemToObject(e,"analysis",analysis_summary());
    diagnostic_emit(e);
    analysis_state.store(ok?Ready:TooShort);
}
}

void motion_run() {
    constexpr size_t max_samples=motion::max_seconds*motion::second_samples; // 10 minutes, 360 KB
    std::unique_ptr<motion::Sample,decltype(&free)> record(static_cast<motion::Sample*>(
        heap_caps_malloc(max_samples*sizeof(motion::Sample),MALLOC_CAP_SPIRAM)),free);
    size_t recorded=0;bool truncated=false;unsigned samples=0,read_errors=0,late=0;
    bmi2_sens_data data{};
    float sum[3]{},point_change=0;unsigned in_point=0;
    const int64_t started=esp_timer_get_time();
    TickType_t wake=xTaskGetTickCount();
    while(!stop.load()) {
        if(xTaskDelayUntil(&wake,pdMS_TO_TICKS(10))==pdFALSE)++late;
        // A failed read repeats the last sample, so the record stays at 100 Hz.
        if(imu_read_checked(data)!=BMI2_OK)++read_errors;
        ++samples;
        const motion::Sample s{data.acc.x,data.acc.y,data.acc.z};
        if(record) {
            if(recorded<max_samples)record.get()[recorded++]=s;
            else truncated=true;
        }
        const float change=motion::magnitude_g(s)-1;
        if(!in_point || std::fabs(change)>std::fabs(point_change))point_change=change;
        sum[0]+=s.x;sum[1]+=s.y;sum[2]+=s.z;
        if(++in_point==5) {
            const Point p{point_change,motion::tilt_deg(sum[0],sum[1],sum[2])};
            portENTER_CRITICAL(&view_lock);points[point_total%point_ring]=p;++point_total;portEXIT_CRITICAL(&view_lock);
            in_point=0;sum[0]=sum[1]=sum[2]=0;
        }
    }
    auto* e=diagnostic_event("motion_session");cJSON_AddStringToObject(e,"result","closed");
    cJSON_AddNumberToObject(e,"duration_ms",(esp_timer_get_time()-started)/1000);
    cJSON_AddNumberToObject(e,"samples",samples);cJSON_AddNumberToObject(e,"recorded",recorded);
    cJSON_AddNumberToObject(e,"read_errors",read_errors);cJSON_AddNumberToObject(e,"late",late);
    cJSON_AddBoolToObject(e,"truncated",truncated);cJSON_AddBoolToObject(e,"record_allocated",record!=nullptr);
    diagnostic_emit(e);
    if(analysis_requested.exchange(false))analyze_session(record.get(),recorded);
}

namespace {
cJSON* rounded(double value,double scale=10) {return cJSON_CreateNumber(std::round(value*scale)/scale);}
cJSON* grams(float g) {return rounded(g,1000);}
// The summary the Mac checks (tools/motion_explain.py FIELDS).
cJSON* analysis_summary() {
    const auto& a=result;auto* o=cJSON_CreateObject();
    cJSON_AddStringToObject(o,"kind","motion");
    cJSON_AddItemToObject(o,"duration_s",rounded(a.duration_s));
    const std::pair<const char*,float> g[]={{"gravity_g",a.gravity_g},{"quiet_g",a.quiet_g},{"threshold_g",a.threshold_g},
        {"peak_g",a.peak_g},{"typical_g",a.typical_g},{"steadiest_g",a.steadiest_g},{"shakiest_g",a.shakiest_g}};
    for(const auto& [key,value]:g)cJSON_AddItemToObject(o,key,grams(value));
    const std::pair<const char*,float> other[]={{"peak_at_s",a.peak_at_s},{"steadiest_at_s",a.steadiest_at_s},
        {"shakiest_at_s",a.shakiest_at_s},{"tilt_min_deg",a.tilt_min_deg},{"tilt_max_deg",a.tilt_max_deg},{"rest_s",a.rest_s}};
    for(const auto& [key,value]:other)cJSON_AddItemToObject(o,key,rounded(value));
    cJSON_AddStringToObject(o,"steadiness",motion::steadiness_name(a.steadiness));
    cJSON_AddNumberToObject(o,"still_s",a.steadiness_s[motion::HeldStill]);
    cJSON_AddNumberToObject(o,"in_hand_s",a.steadiness_s[motion::InHand]);
    cJSON_AddNumberToObject(o,"moving_s",a.steadiness_s[motion::Moving]);
    cJSON_AddStringToObject(o,"orientation",motion::orientation_name(a.orientation));
    cJSON_AddNumberToObject(o,"flat_s",a.orientation_s[motion::Flat]);
    cJSON_AddNumberToObject(o,"tilted_s",a.orientation_s[motion::Tilted]);
    cJSON_AddNumberToObject(o,"upright_s",a.orientation_s[motion::Upright]);
    cJSON_AddNumberToObject(o,"event_count",a.event_count);
    auto* events=cJSON_AddArrayToObject(o,"events");
    for(unsigned i=0;i<std::min<unsigned>(a.event_count,motion::max_events);++i) {
        const auto& v=a.events[i];auto* e=cJSON_CreateObject();
        cJSON_AddItemToObject(e,"start_s",rounded(v.start_s,100));cJSON_AddItemToObject(e,"duration_s",rounded(v.duration_s,100));
        cJSON_AddItemToObject(e,"peak_g",grams(v.peak_g));cJSON_AddItemToArray(events,e);
    }
    if(a.vibration) {
        auto* v=cJSON_AddObjectToObject(o,"vibration");
        cJSON_AddItemToObject(v,"vibration_hz",rounded(a.vibration_hz));
        cJSON_AddItemToObject(v,"vibration_mg",rounded(a.vibration_g*1000));
    } else cJSON_AddNullToObject(o,"vibration");
    auto* movement=cJSON_AddArrayToObject(o,"movement_1s_mg");
    auto* tilt=cJSON_AddArrayToObject(o,"tilt_1s_deg");
    for(unsigned i=0;i<a.seconds;++i) {
        cJSON_AddItemToArray(movement,rounded(a.second[i].movement_g*1000));
        cJSON_AddItemToArray(tilt,rounded(a.second[i].tilt_deg));
    }
    return o;
}
void new_session(char* out,size_t size) {
    snprintf(out,size,"ma-%08lx%08lx%08lx%08lx",static_cast<unsigned long>(esp_random()),static_cast<unsigned long>(esp_random()),
             static_cast<unsigned long>(esp_random()),static_cast<unsigned long>(esp_random()));
}
// Media task -> screen; takes the display lock for each update.
void explain_progress(const char* stage,const char*,const char* reply) {
    if(!bsp_display_lock(1000))return;
    if(stage)lv_label_set_text(status_label,stage);
    if(reply) {
        const std::string shown="Agent: "+std::string(reply)+"\n\n"+events_text;
        lv_label_set_text(events_label,shown.c_str());lv_obj_scroll_to_y(lv_obj_get_parent(events_label),0,LV_ANIM_OFF);
        lv_label_set_text(status_label,"The agent's reading is below. Stop voice ends the speech.");
    }
    bsp_display_unlock();
}
void restore_buttons(const char* status) {
    if(!bsp_display_lock(1000))return;
    lv_label_set_text(status_label,status);lv_label_set_text(explain_label,"Explain");
    for(auto* b:{explain_button,again_button})lv_obj_remove_state(b,LV_STATE_DISABLED);
    bsp_display_unlock();
}
}

void motion_explain(const char* boot) {
    char session[40];new_session(session,sizeof(session));
    AnalysisExplainHooks hooks{explain_progress};
    AnalysisExplainResult out;
    const bool ok=analysis_state.load()==Ready &&
        investigation_explain_analysis(boot,session,nullptr,analysis_summary(),hooks,out);
    explaining.store(false);
    restore_buttons(ok?"Tap Explain to ask again.":out.error.empty()?"Nothing to explain yet.":out.error.c_str());
}
