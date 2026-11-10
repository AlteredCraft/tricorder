#include "power.h"
#include "power_analysis.h"
#include "sound_analysis.h"
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
lv_obj_t *panel,*volts_label,*amps_label,*watts_label,*hint_label,*screen_label,*trace_chart,*volts_chart,*scale_top,*scale_bottom;
lv_chart_series_t *trace_series,*volts_series;
// Media owner -> LVGL timer: one point per 10 Hz sample.
struct Point {float v,a;};
constexpr size_t point_ring=64;
portMUX_TYPE view_lock=portMUX_INITIALIZER_UNLOCKED;
Point points[point_ring];unsigned point_total=0; // view_lock
// LVGL task only.
constexpr size_t trace_points=600; // 60 s
float recent[trace_points];size_t recent_next=0;
unsigned drawn_total=0,draws=0;float shown_span=0;bool shown_negative=false;int shown_source=-1;
// The backlight level the Screen button set (LVGL task); the run loop marks each change.
constexpr int default_brightness=50;
int brightness=default_brightness;
std::atomic<int> brightness_request{-1};
// Analysis: the media owner writes result, then sets analysis_state; the LVGL timer reads
// it only after that.
std::atomic<bool> analysis_requested{false};
enum AnalysisState {Idle,Pending,Ready,TooShort};
std::atomic<int> analysis_state{Idle};
power::Analysis result;
bool analysis_shown=false; // LVGL task
lv_obj_t *analysis_panel,*analysis_heading,*summary_label,*changes_label,*strip_chart,*strip_end,*again_button;
lv_obj_t *status_label,*explain_button,*explain_label;
lv_chart_series_t *strip_series;
std::string changes_text; // LVGL task: the change list, shown under the agent's reading
std::atomic<bool> explaining{false};

int32_t milli(float value) {return static_cast<int32_t>(std::lround(value*1000));}
void set_span(float span,bool negative) {
    shown_span=span;shown_negative=negative;
    lv_chart_set_range(trace_chart,LV_CHART_AXIS_PRIMARY_Y,negative?-milli(span):0,milli(span));
    char text[24],value[16];power::a_text(span,value,sizeof(value));
    lv_label_set_text(scale_top,value);
    if(negative){snprintf(text,sizeof(text),"-%s",value);lv_label_set_text(scale_bottom,text);}
    else lv_label_set_text(scale_bottom,"0");
}
void show_hint(power::Source source) {
    if(static_cast<int>(source)==shown_source)return;
    shown_source=source;
    lv_label_set_text(hint_label,source==power::Battery?"Running on battery. Tap Screen to change the backlight and watch the draw.":
        source==power::Charging?"Charging the battery from USB. The device itself runs from USB, so its draw does not show here.":
        "No battery current: on USB the device runs from USB. Unplug it to see what the device draws.");
}
void draw(lv_timer_t*) {
    if(lv_obj_has_flag(panel,LV_OBJ_FLAG_HIDDEN))return;
    Point fresh[point_ring];unsigned total,count;
    portENTER_CRITICAL(&view_lock);
    total=point_total;count=std::min<unsigned>(total-drawn_total,point_ring);
    for(unsigned i=0;i<count;++i)fresh[i]=points[(total-count+i)%point_ring];
    portEXIT_CRITICAL(&view_lock);
    if(!count)return;
    drawn_total=total;++draws;
    for(unsigned i=0;i<count;++i) {
        const auto& p=fresh[i];
        lv_chart_set_next_value(trace_chart,trace_series,milli(p.a));
        lv_chart_set_next_value(volts_chart,volts_series,milli(p.v));
        recent[recent_next]=p.a;recent_next=(recent_next+1)%trace_points;
    }
    const auto [low,high]=std::minmax_element(recent,recent+trace_points);
    const float largest=std::max(std::fabs(*low),std::fabs(*high));
    float span=4;
    for(float s:{0.1f,0.2f,0.5f,1.0f,2.0f})if(largest<=0.9f*s){span=s;break;}
    const bool negative=*low<-power::no_current_a;
    if(span!=shown_span || negative!=shown_negative)set_span(span,negative);
    const auto& last=fresh[count-1];char text[32],value[16];
    snprintf(text,sizeof(text),"%.2f V",last.v);lv_label_set_text(volts_label,text);
    power::a_text(std::fabs(last.a),value,sizeof(value));
    snprintf(text,sizeof(text),"%s%s",last.a<=-power::no_current_a?"In ":"",value);lv_label_set_text(amps_label,text);
    power::w_text(std::fabs(last.a*last.v),value,sizeof(value));lv_label_set_text(watts_label,value);
    show_hint(power::source_of(last.a));
}
void log_control(const char* control) {
    auto* e=diagnostic_event("power_control");cJSON_AddStringToObject(e,"control",control);
    cJSON_AddNumberToObject(e,"draws",draws);cJSON_AddNumberToObject(e,"brightness",brightness);diagnostic_emit(e);
}
void set_brightness(int level) {
    brightness=level;bsp_display_brightness_set(level);
    char text[24];snprintf(text,sizeof(text),"Screen %d%%",level);lv_label_set_text(screen_label,text);
}
// 50 -> 100 -> 20 -> 50: one feature whose draw the analysis can measure.
void screen_clicked(lv_event_t*) {
    set_brightness(brightness==default_brightness?100:brightness==100?20:default_brightness);
    brightness_request.store(brightness);log_control("screen");
}
void restore_brightness() {if(brightness!=default_brightness)set_brightness(default_brightness);}
void back(lv_event_t*) {
    stop.store(true);restore_brightness();lv_obj_add_flag(panel,LV_OBJ_FLAG_HIDDEN);log_control("back");home_returned("power");
}
void show_analysis() {
    analysis_shown=true;
    lv_label_set_text(analysis_heading,"Power analysis");
    if(analysis_state.load()==TooShort) {
        lv_label_set_text(summary_label,"Measure for at least a few seconds, then tap Analysis.");
        lv_obj_remove_state(again_button,LV_STATE_DISABLED);return;
    }
    const auto& a=result;char when[16],x[16],y[16],line[200];
    std::string summary,changes;
    sound::clock_text(a.duration_s,when,sizeof(when));
    snprintf(line,sizeof(line),"Measured %s\n\nMostly: %s\n",when,power::source_name(a.source));summary+=line;
    snprintf(line,sizeof(line),"On battery %u s, charging %u s, no current %u s\n\n",a.battery_s,a.charging_s,a.no_current_s);summary+=line;
    snprintf(line,sizeof(line),"Battery %.2f V to %.2f V (lowest %.2f V)\n",a.v_start,a.v_end,a.v_min);summary+=line;
    if(a.battery_pct>=0){snprintf(line,sizeof(line),"About %.0f%% full, roughly, from the volts\n",a.battery_pct);summary+=line;}
    summary+="\n";
    if(a.battery_s) {
        power::a_text(a.draw_typical_a,x,sizeof(x));power::w_text(a.power_typical_w,y,sizeof(y));
        snprintf(line,sizeof(line),"Draw: typical %s (%s)\n",x,y);summary+=line;
        power::a_text(a.draw_min_a,x,sizeof(x));power::a_text(a.draw_max_a,y,sizeof(y));
        sound::clock_text(a.draw_max_at_s,when,sizeof(when));
        snprintf(line,sizeof(line),"Lowest %s, highest %s at %s\n",x,y,when);summary+=line;
        power::w_text(a.power_max_w,y,sizeof(y));
        snprintf(line,sizeof(line),"Highest power %s\n",y);summary+=line;
        snprintf(line,sizeof(line),"Used %.1f mAh (%.0f mWh)\n",a.used_mah,a.used_mwh);summary+=line;
    } else summary+="Draw: not measured; the device was not on battery.\n";
    if(a.charging_s) {
        power::a_text(a.charge_typical_a,x,sizeof(x));
        snprintf(line,sizeof(line),"Charging: typical %s in, %.1f mAh in\n",x,a.charged_mah);summary+=line;
    }
    summary+="\nCurrent is what flows out of the battery pack; charging flows in. On USB the device runs from USB and "
             "its draw does not pass this sensor. The readings are not calibrated.";
    lv_label_set_text(summary_label,summary.c_str());
    power::a_text(power::step_a,x,sizeof(x));
    if(!a.step_count){snprintf(line,sizeof(line),"No changes in draw: the current stayed within %s.\n\n",x);changes=line;}
    else {
        snprintf(line,sizeof(line),"%u change%s in draw (%s or more, held %u s)\n\n",a.step_count,a.step_count==1?"":"s",x,
                 unsigned(power::step_hold_s));changes+=line;
        for(unsigned i=0;i<std::min<unsigned>(a.step_count,power::max_steps);++i) {
            const auto& s=a.steps[i];
            sound::clock_text(s.at_s,when,sizeof(when));power::a_text(s.from_a,x,sizeof(x));power::a_text(s.to_a,y,sizeof(y));
            snprintf(line,sizeof(line),"%u.  %s   %s to %s\n",i+1,when,x,y);changes+=line;
        }
        if(a.step_count>power::max_steps){snprintf(line,sizeof(line),"and %u more\n",a.step_count-unsigned(power::max_steps));changes+=line;}
        changes+="\n";
    }
    if(a.change_count) {
        changes+="Screen changes\n";
        for(unsigned i=0;i<a.change_count;++i) {
            const auto& c=a.changes[i];
            sound::clock_text(c.at_s,when,sizeof(when));power::a_text(c.before_a,x,sizeof(x));power::a_text(c.after_a,y,sizeof(y));
            snprintf(line,sizeof(line),"%s   to %u%%: %s before, %s after\n",when,c.brightness,x,y);changes+=line;
        }
    } else changes+="Screen changes: none measured. Tap Screen while measuring, 3 s or more apart.";
    changes_text=changes;lv_label_set_text(changes_label,changes.c_str());
    lv_label_set_text(status_label,"Tap Explain to have the agent read this analysis.");
    lv_obj_remove_state(explain_button,LV_STATE_DISABLED);
    // Draw per second in mA.
    float low=0,high=0.1f;
    for(unsigned k=0;k<a.seconds;++k){low=std::min(low,a.second[k].a);high=std::max(high,a.second[k].a);}
    lv_chart_set_point_count(strip_chart,a.seconds);
    lv_chart_set_range(strip_chart,LV_CHART_AXIS_PRIMARY_Y,milli(low*1.1f),milli(high*1.1f));
    for(unsigned k=0;k<a.seconds;++k)lv_chart_set_value_by_id(strip_chart,strip_series,k,milli(a.second[k].a));
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
    restore_brightness();
    lv_label_set_text(analysis_heading,"Analyzing...");lv_label_set_text(summary_label,"");lv_label_set_text(changes_label,"");
    lv_obj_add_flag(strip_chart,LV_OBJ_FLAG_HIDDEN);lv_label_set_text(strip_end,"");
    lv_obj_add_state(again_button,LV_STATE_DISABLED); // until the sampling loop has ended
    lv_obj_add_state(explain_button,LV_STATE_DISABLED);
    lv_label_set_text(status_label,"");lv_label_set_text(explain_label,"Explain");
    lv_obj_remove_flag(analysis_panel,LV_OBJ_FLAG_HIDDEN);lv_obj_move_foreground(analysis_panel);
    log_control("analysis");
}
void measure_again(lv_event_t*) {
    investigation_stop_speech();lv_obj_add_flag(analysis_panel,LV_OBJ_FLAG_HIDDEN);log_control("measure_again");power_ui_open();
}
void send_media(uint8_t command) {
    if(xQueueSend(media,&command,0)!=pdTRUE) {
        auto* e=diagnostic_event("power_session");cJSON_AddStringToObject(e,"result","queue_full");
        cJSON_AddNumberToObject(e,"command",command);diagnostic_emit(e);
    }
}
// Explain: while the agent answers or speaks, the button stops the voice.
void explain_clicked(lv_event_t*) {
    if(explaining.load()){investigation_stop_speech();log_control("explain_stop_voice");return;}
    explaining.store(true);lv_label_set_text(explain_label,"Stop voice");
    lv_obj_add_state(again_button,LV_STATE_DISABLED);
    log_control("explain");send_media(power_explain_command);
}
void analysis_home(lv_event_t*) {
    investigation_stop_speech();
    lv_obj_add_flag(analysis_panel,LV_OBJ_FLAG_HIDDEN);lv_obj_add_flag(panel,LV_OBJ_FLAG_HIDDEN);
    log_control("analysis_home");home_returned("power_analysis");
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

void power_ui_init(lv_obj_t* screen,QueueHandle_t media_commands) {
    media=media_commands;
    panel=panel_base(screen);
    text(panel,"Power",24,20,&lv_font_montserrat_40,0xffffff);
    volts_label=text(panel,"-- V",190,26,&lv_font_montserrat_32,0x4fc3f7);
    amps_label=text(panel,"-- A",370,26,&lv_font_montserrat_32,0xffb74d);
    watts_label=text(panel,"-- W",550,26,&lv_font_montserrat_32,0x66bb6a);
    button(panel,"Analysis",690,analysis_clicked);
    screen_label=button(panel,"Screen 50%",886,screen_clicked);
    button(panel,"Home",1082,back);
    hint_label=text(panel,"",24,84,&lv_font_montserrat_20,0x90a4ae);
    lv_obj_set_width(hint_label,1232);lv_label_set_long_mode(hint_label,LV_LABEL_LONG_DOT);

    constexpr int chart_x=130,chart_w=1120,trace_y=120,trace_h=290,volts_y=470,volts_h=180;
    trace_chart=chart(panel,chart_x,trace_y,chart_w,trace_h);
    lv_chart_set_point_count(trace_chart,trace_points);lv_chart_set_update_mode(trace_chart,LV_CHART_UPDATE_MODE_SHIFT);
    trace_series=lv_chart_add_series(trace_chart,lv_color_hex(0xffb74d),LV_CHART_AXIS_PRIMARY_Y);
    scale_top=text(panel,"",20,trace_y-4,&lv_font_montserrat_22,0x90a4ae);
    scale_bottom=text(panel,"",20,trace_y+trace_h-24,&lv_font_montserrat_22,0x90a4ae);
    text(panel,"Battery current (orange), last 60 s; out of the battery up, charging down",chart_x,trace_y+trace_h+10,
         &lv_font_montserrat_22,0xffb74d);
    volts_chart=chart(panel,chart_x,volts_y,chart_w,volts_h);lv_chart_set_div_line_count(volts_chart,3,0);
    lv_chart_set_point_count(volts_chart,trace_points);lv_chart_set_update_mode(volts_chart,LV_CHART_UPDATE_MODE_SHIFT);
    lv_chart_set_range(volts_chart,LV_CHART_AXIS_PRIMARY_Y,6000,8600);
    volts_series=lv_chart_add_series(volts_chart,lv_color_hex(0x4fc3f7),LV_CHART_AXIS_PRIMARY_Y);
    text(panel,"8.6 V",20,volts_y-4,&lv_font_montserrat_22,0x90a4ae);
    text(panel,"7.3 V",20,volts_y+volts_h/2-12,&lv_font_montserrat_22,0x90a4ae);
    text(panel,"6.0 V",20,volts_y+volts_h-24,&lv_font_montserrat_22,0x90a4ae);
    text(panel,"Battery volts (blue): about 8.4 V full, 6.6 V empty",chart_x,volts_y+volts_h+10,&lv_font_montserrat_22,0x4fc3f7);
    lv_timer_create(draw,50,nullptr);
    lv_obj_add_flag(panel,LV_OBJ_FLAG_HIDDEN);

    analysis_panel=panel_base(screen);
    analysis_heading=text(analysis_panel,"Power analysis",24,20,&lv_font_montserrat_40,0xffffff);
    explain_label=button(analysis_panel,"Explain",690,explain_clicked);explain_button=lv_obj_get_parent(explain_label);
    lv_obj_add_state(explain_button,LV_STATE_DISABLED);
    status_label=text(analysis_panel,"",24,82,&lv_font_montserrat_20,0x4fc3f7);
    lv_obj_set_width(status_label,1232);lv_label_set_long_mode(status_label,LV_LABEL_LONG_DOT);
    again_button=lv_obj_get_parent(button(analysis_panel,"Measure again",886,measure_again));
    button(analysis_panel,"Home",1082,analysis_home);
    summary_label=scroll_box(analysis_panel,24,114,470,586,&lv_font_montserrat_24);
    strip_chart=chart(analysis_panel,520,114,736,222);lv_chart_set_div_line_count(strip_chart,4,0);
    lv_obj_set_style_line_width(strip_chart,2,LV_PART_ITEMS);
    strip_series=lv_chart_add_series(strip_chart,lv_color_hex(0xffb74d),LV_CHART_AXIS_PRIMARY_Y);
    text(analysis_panel,"0:00",520,342,&lv_font_montserrat_20,0x90a4ae);
    strip_end=text(analysis_panel,"",1196,342,&lv_font_montserrat_20,0x90a4ae);
    text(analysis_panel,"Battery current, each second",640,342,&lv_font_montserrat_20,0xffb74d);
    changes_label=scroll_box(analysis_panel,520,378,736,322,&lv_font_montserrat_22);
    lv_timer_create(draw_analysis,100,nullptr);
    lv_obj_add_flag(analysis_panel,LV_OBJ_FLAG_HIDDEN);
}

void power_ui_open() {
    draws=0;shown_span=0;shown_negative=false;shown_source=-1;recent_next=0;
    for(auto& r:recent)r=0;
    lv_label_set_text(volts_label,"-- V");lv_label_set_text(amps_label,"-- A");lv_label_set_text(watts_label,"-- W");
    lv_label_set_text(hint_label,"");set_span(0.1f,false);
    lv_chart_set_all_value(trace_chart,trace_series,LV_CHART_POINT_NONE);
    lv_chart_set_all_value(volts_chart,volts_series,LV_CHART_POINT_NONE);
    portENTER_CRITICAL(&view_lock);drawn_total=point_total;portEXIT_CRITICAL(&view_lock);
    brightness_request.store(-1);
    lv_obj_remove_flag(panel,LV_OBJ_FLAG_HIDDEN);lv_obj_move_foreground(panel);
    stop.store(false);send_media(power_media_command);
}

namespace {
// Media owner, after sampling stops.
cJSON* analysis_summary();
void analyze_session(const power::Sample* samples,size_t n,const power::Mark* marks,size_t mark_count) {
    const int64_t started=esp_timer_get_time();
    std::unique_ptr<float,decltype(&free)> scratch(static_cast<float*>(
        heap_caps_malloc((n?n:1)*sizeof(float),MALLOC_CAP_SPIRAM)),free);
    const bool ok=samples && scratch && power::analyze(samples,n,marks,mark_count,scratch.get(),result);
    const int64_t compute_us=esp_timer_get_time()-started;
    auto* e=diagnostic_event("power_analysis");
    cJSON_AddStringToObject(e,"result",ok?"ready":"too_short");cJSON_AddNumberToObject(e,"samples",n);
    cJSON_AddNumberToObject(e,"marks",mark_count);cJSON_AddNumberToObject(e,"compute_us",compute_us);
    if(ok)cJSON_AddItemToObject(e,"analysis",analysis_summary());
    diagnostic_emit(e);
    analysis_state.store(ok?Ready:TooShort);
}
}

void power_run() {
    constexpr size_t max_samples=power::max_seconds*power::second_samples; // 10 minutes, 48 KB
    constexpr size_t max_marks=32;
    std::unique_ptr<power::Sample,decltype(&free)> record(static_cast<power::Sample*>(
        heap_caps_malloc(max_samples*sizeof(power::Sample),MALLOC_CAP_SPIRAM)),free);
    power::Mark marks[max_marks];size_t mark_count=0;
    size_t recorded=0;bool truncated=false;unsigned samples=0,read_errors=0,late=0;
    float bus_v=0,shunt_a=0;
    const int64_t started=esp_timer_get_time();
    TickType_t wake=xTaskGetTickCount();
    while(!stop.load()) {
        if(xTaskDelayUntil(&wake,pdMS_TO_TICKS(100))==pdFALSE)++late;
        // A failed read repeats the last sample, so the record stays at 10 Hz.
        if(!diagnostic_power_read(bus_v,shunt_a))++read_errors;
        ++samples;
        const power::Sample s{bus_v,shunt_a};
        const int level=brightness_request.exchange(-1);
        if(level>=0 && mark_count<max_marks)marks[mark_count++]={recorded,static_cast<uint8_t>(level)};
        if(record) {
            if(recorded<max_samples)record.get()[recorded++]=s;
            else truncated=true;
        }
        portENTER_CRITICAL(&view_lock);points[point_total%point_ring]={s.v,s.a};++point_total;portEXIT_CRITICAL(&view_lock);
    }
    auto* e=diagnostic_event("power_session");cJSON_AddStringToObject(e,"result","closed");
    cJSON_AddNumberToObject(e,"duration_ms",(esp_timer_get_time()-started)/1000);
    cJSON_AddNumberToObject(e,"samples",samples);cJSON_AddNumberToObject(e,"recorded",recorded);
    cJSON_AddNumberToObject(e,"marks",mark_count);
    cJSON_AddNumberToObject(e,"read_errors",read_errors);cJSON_AddNumberToObject(e,"late",late);
    cJSON_AddBoolToObject(e,"truncated",truncated);cJSON_AddBoolToObject(e,"record_allocated",record!=nullptr);
    diagnostic_emit(e);
    if(analysis_requested.exchange(false))analyze_session(record.get(),recorded,marks,mark_count);
}

namespace {
cJSON* rounded(double value,double scale=10) {return cJSON_CreateNumber(std::round(value*scale)/scale);}
cJSON* milliamps(float a) {return rounded(a*1000,1);}
// The summary the Mac checks (tools/power_explain.py FIELDS).
cJSON* analysis_summary() {
    const auto& a=result;auto* o=cJSON_CreateObject();
    cJSON_AddStringToObject(o,"kind","power");
    cJSON_AddItemToObject(o,"duration_s",rounded(a.duration_s));
    cJSON_AddStringToObject(o,"source",power::source_name(a.source));
    cJSON_AddNumberToObject(o,"battery_s",a.battery_s);
    cJSON_AddNumberToObject(o,"charging_s",a.charging_s);
    cJSON_AddNumberToObject(o,"no_current_s",a.no_current_s);
    const std::pair<const char*,float> volts[]={{"volts_start_v",a.v_start},{"volts_end_v",a.v_end},{"volts_min_v",a.v_min},{"volts_max_v",a.v_max}};
    for(const auto& [key,value]:volts)cJSON_AddItemToObject(o,key,rounded(value,100));
    const std::pair<const char*,float> amps[]={{"draw_typical_ma",a.draw_typical_a},{"draw_min_ma",a.draw_min_a},
        {"draw_max_ma",a.draw_max_a},{"charge_typical_ma",a.charge_typical_a}};
    for(const auto& [key,value]:amps)cJSON_AddItemToObject(o,key,milliamps(value));
    cJSON_AddItemToObject(o,"draw_max_at_s",rounded(a.draw_max_at_s));
    cJSON_AddItemToObject(o,"power_typical_mw",rounded(a.power_typical_w*1000,1));
    cJSON_AddItemToObject(o,"power_max_mw",rounded(a.power_max_w*1000,1));
    cJSON_AddItemToObject(o,"used_mah",rounded(a.used_mah));
    cJSON_AddItemToObject(o,"used_mwh",rounded(a.used_mwh));
    cJSON_AddItemToObject(o,"charged_mah",rounded(a.charged_mah));
    if(a.battery_pct>=0)cJSON_AddItemToObject(o,"battery_pct",rounded(a.battery_pct,1));
    else cJSON_AddNullToObject(o,"battery_pct");
    cJSON_AddNumberToObject(o,"step_count",a.step_count);
    auto* steps=cJSON_AddArrayToObject(o,"steps");
    for(unsigned i=0;i<std::min<unsigned>(a.step_count,power::max_steps);++i) {
        const auto& s=a.steps[i];auto* e=cJSON_CreateObject();
        cJSON_AddItemToObject(e,"at_s",rounded(s.at_s));cJSON_AddItemToObject(e,"from_ma",milliamps(s.from_a));
        cJSON_AddItemToObject(e,"to_ma",milliamps(s.to_a));cJSON_AddItemToArray(steps,e);
    }
    auto* changes=cJSON_AddArrayToObject(o,"screen_changes");
    for(unsigned i=0;i<a.change_count;++i) {
        const auto& c=a.changes[i];auto* e=cJSON_CreateObject();
        cJSON_AddItemToObject(e,"at_s",rounded(c.at_s));cJSON_AddNumberToObject(e,"brightness_pct",c.brightness);
        cJSON_AddItemToObject(e,"before_ma",milliamps(c.before_a));cJSON_AddItemToObject(e,"after_ma",milliamps(c.after_a));
        cJSON_AddItemToArray(changes,e);
    }
    auto* current=cJSON_AddArrayToObject(o,"current_1s_ma");
    auto* v=cJSON_AddArrayToObject(o,"volts_1s_v");
    for(unsigned k=0;k<a.seconds;++k) {
        cJSON_AddItemToArray(current,milliamps(a.second[k].a));
        cJSON_AddItemToArray(v,rounded(a.second[k].v,100));
    }
    return o;
}
void new_session(char* out,size_t size) {
    snprintf(out,size,"pw-%08lx%08lx%08lx%08lx",static_cast<unsigned long>(esp_random()),static_cast<unsigned long>(esp_random()),
             static_cast<unsigned long>(esp_random()),static_cast<unsigned long>(esp_random()));
}
// Media task -> screen; takes the display lock for each update.
void explain_progress(const char* stage,const char*,const char* reply) {
    if(!bsp_display_lock(1000))return;
    if(stage)lv_label_set_text(status_label,stage);
    if(reply) {
        const std::string shown="Agent: "+std::string(reply)+"\n\n"+changes_text;
        lv_label_set_text(changes_label,shown.c_str());lv_obj_scroll_to_y(lv_obj_get_parent(changes_label),0,LV_ANIM_OFF);
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

void power_explain(const char* boot) {
    char session[40];new_session(session,sizeof(session));
    AnalysisExplainHooks hooks{explain_progress};
    AnalysisExplainResult out;
    const bool ok=analysis_state.load()==Ready &&
        investigation_explain_analysis(boot,session,nullptr,analysis_summary(),hooks,out);
    explaining.store(false);
    restore_buttons(ok?"Tap Explain to ask again.":out.error.empty()?"Nothing to explain yet.":out.error.c_str());
}
