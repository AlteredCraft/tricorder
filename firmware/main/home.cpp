#include "home.h"
#include "home_model.h"
#include "home_info.h"
#include "investigation.h"
#include "network.h"
#include "sound.h"
#include "diagnostic_events.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstring>
#include <initializer_list>

namespace {
enum Opens {None,Investigate,Sound,Setup,Diagnostics};
// What each tile opens, in home::tile_text order (names, notes and info text).
constexpr Opens opens_for[home::tile_count]={Investigate,Sound,None,None,None,None,Setup,Diagnostics};
constexpr unsigned motion_tile=3,power_tile=4,audio_tile=5,setup_tile=6;
lv_obj_t *home_panel,*readings[home::tile_count],*info_panel,*info_title,*info_scroll,*info_text;
// The open info page (LVGL task): tile, when it opened, furthest scroll.
int info_tile=-1;int64_t info_opened_us=0;int32_t info_max_scroll=0;
portMUX_TYPE readings_lock=portMUX_INITIALIZER_UNLOCKED;
struct Readings {float tilt=NAN,bus_v=NAN,shunt_a=0;bool headphones=false,fresh=false;} latest; // readings_lock
uint32_t shown_ipv4=1; // LVGL task; 1 forces the first draw
std::atomic<int64_t> touch_down_us{0};
// One navigation waiting for the refresh that shows it (LVGL task only).
const char *nav_from=nullptr,*nav_to=nullptr;int64_t nav_pressed=0,nav_handled=0;

void note_nav(const char* from,const char* to) {
    nav_from=from;nav_to=to;nav_pressed=touch_down_us.load();nav_handled=esp_timer_get_time();
}
// F-0001 T1 telemetry: touch-down -> handler -> end of the refresh that draws the new screen.
void refreshed(lv_event_t*) {
    if(!nav_from)return;
    const int64_t shown=esp_timer_get_time();
    auto* e=diagnostic_event("ui_nav");
    cJSON_AddStringToObject(e,"from",nav_from);cJSON_AddStringToObject(e,"to",nav_to);
    cJSON_AddNumberToObject(e,"pressed_us",nav_pressed);cJSON_AddNumberToObject(e,"handled_us",nav_handled);
    cJSON_AddNumberToObject(e,"shown_us",shown);
    if(nav_pressed>0 && nav_pressed<=nav_handled)cJSON_AddNumberToObject(e,"touch_to_shown_ms",(shown-nav_pressed)/1000.0);
    diagnostic_emit(e);nav_from=nullptr;
}
void pressed(lv_event_t*) {touch_down_us.store(esp_timer_get_time());}
void show_home(bool visible) {
    if(visible){lv_obj_remove_flag(home_panel,LV_OBJ_FLAG_HIDDEN);lv_obj_move_foreground(home_panel);}
    else lv_obj_add_flag(home_panel,LV_OBJ_FLAG_HIDDEN);
}
void tile_clicked(lv_event_t* ev) {
    const auto index=reinterpret_cast<uintptr_t>(lv_event_get_user_data(ev));
    const auto& text=home::tile_text[index];const Opens opens=opens_for[index];
    if(opens==None) {
        auto* e=diagnostic_event("home_tap");cJSON_AddStringToObject(e,"tile",text.name);
        cJSON_AddBoolToObject(e,"opens",false);diagnostic_emit(e);return;
    }
    if(opens==Investigate){investigation_ui_open();note_nav("home","investigate");}
    else if(opens==Sound){sound_ui_open();note_nav("home","sound");}
    else if(opens==Setup){investigation_setup_open();note_nav("home","setup");}
    else {show_home(false);note_nav("home","diagnostics");}
}
void info_open(lv_event_t* ev) {
    const auto index=reinterpret_cast<uintptr_t>(lv_event_get_user_data(ev));
    info_tile=index;info_opened_us=esp_timer_get_time();info_max_scroll=0;
    lv_label_set_text(info_title,home::tile_text[index].name);lv_label_set_text(info_text,home::tile_text[index].info);
    lv_obj_scroll_to_y(info_scroll,0,LV_ANIM_OFF);
    lv_obj_remove_flag(info_panel,LV_OBJ_FLAG_HIDDEN);lv_obj_move_foreground(info_panel);
    note_nav("home","info");
}
void info_scrolled(lv_event_t*) {info_max_scroll=std::max(info_max_scroll,lv_obj_get_scroll_y(info_scroll));}
// F-0001 T3 telemetry: how long a page stayed open and whether it was read to the end.
void info_close(lv_event_t*) {
    lv_obj_update_layout(info_scroll);
    const int32_t scrollable=lv_obj_get_scroll_y(info_scroll)+lv_obj_get_scroll_bottom(info_scroll);
    auto* e=diagnostic_event("home_info");cJSON_AddStringToObject(e,"tile",home::tile_text[info_tile].name);
    cJSON_AddNumberToObject(e,"open_ms",(esp_timer_get_time()-info_opened_us)/1000);
    cJSON_AddNumberToObject(e,"max_scroll_px",info_max_scroll);cJSON_AddNumberToObject(e,"scrollable_px",scrollable);
    cJSON_AddBoolToObject(e,"reached_end",info_max_scroll>=scrollable-8);diagnostic_emit(e);
    lv_obj_add_flag(info_panel,LV_OBJ_FLAG_HIDDEN);note_nav("info","home");
}
void home_clicked(lv_event_t*) {show_home(true);note_nav("diagnostics","home");}
// Taps on the panel itself hit no tile.
void missed(lv_event_t* ev) {
    if(lv_event_get_target(ev)!=home_panel)return;
    lv_point_t point{};if(auto* indev=lv_event_get_indev(ev))lv_indev_get_point(indev,&point);
    auto* e=diagnostic_event("home_miss");cJSON_AddNumberToObject(e,"x",point.x);cJSON_AddNumberToObject(e,"y",point.y);
    diagnostic_emit(e);
}
void draw(lv_timer_t*) {
    char text[64];
    const uint32_t ipv4=network_ipv4();
    if(ipv4!=shown_ipv4){home::network_text(ipv4,text,sizeof(text));lv_label_set_text(readings[setup_tile],text);shown_ipv4=ipv4;}
    Readings r;
    portENTER_CRITICAL(&readings_lock);r=latest;latest.fresh=false;portEXIT_CRITICAL(&readings_lock);
    if(!r.fresh)return;
    home::motion_text(r.tilt,text,sizeof(text));lv_label_set_text(readings[motion_tile],text);
    home::power_text(r.bus_v,r.shunt_a,text,sizeof(text));lv_label_set_text(readings[power_tile],text);
    lv_label_set_text(readings[audio_tile],r.headphones?"Headphones":"Speaker");
}
lv_obj_t* label(lv_obj_t* parent,const char* value,const lv_font_t* font,uint32_t color) {
    auto* l=lv_label_create(parent);lv_label_set_text(l,value);
    lv_obj_set_style_text_font(l,font,0);lv_obj_set_style_text_color(l,lv_color_hex(color),0);return l;
}
}

void home_ui_init(lv_obj_t* screen) {
    home_panel=lv_obj_create(screen);lv_obj_remove_style_all(home_panel);
    lv_obj_set_size(home_panel,home::screen_w,home::screen_h);lv_obj_set_pos(home_panel,0,0);
    lv_obj_set_style_bg_color(home_panel,lv_color_hex(0x101418),0);lv_obj_set_style_bg_opa(home_panel,LV_OPA_COVER,0);
    lv_obj_remove_flag(home_panel,LV_OBJ_FLAG_SCROLLABLE);lv_obj_add_flag(home_panel,LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_event_cb(home_panel,missed,LV_EVENT_PRESSED,nullptr);
    auto* title=label(home_panel,"Tricorder",&lv_font_montserrat_40,0xffffff);
    lv_obj_set_pos(title,home::margin,(home::header-44)/2);
    for(unsigned i=0;i<home::tile_count;++i) {
        const auto r=home::tile(i);const bool opens=opens_for[i]!=None;const auto& text=home::tile_text[i];
        auto* t=lv_obj_create(home_panel);lv_obj_set_pos(t,r.x,r.y);lv_obj_set_size(t,r.w,r.h);
        lv_obj_remove_flag(t,LV_OBJ_FLAG_SCROLLABLE);
        lv_obj_set_style_radius(t,16,0);lv_obj_set_style_pad_all(t,20,0);
        lv_obj_set_style_bg_color(t,lv_color_hex(opens?0x1e2a33:0x161c21),0);
        lv_obj_set_style_bg_color(t,lv_color_hex(0x2e4452),LV_STATE_PRESSED);
        lv_obj_set_style_border_width(t,opens?3:1,0);
        lv_obj_set_style_border_color(t,lv_color_hex(opens?0x4fc3f7:0x37474f),0);
        lv_obj_add_event_cb(t,tile_clicked,LV_EVENT_CLICKED,reinterpret_cast<void*>(static_cast<uintptr_t>(i)));
        auto* name=label(t,text.name,&lv_font_montserrat_32,opens?0xffffff:0xb0bec5);lv_obj_set_pos(name,0,0);
        auto* note=label(t,text.note,&lv_font_montserrat_20,opens?0x4fc3f7:0x78909c);lv_obj_set_pos(note,0,46);
        if(text.info) {
            // Its own target: a tap here opens the info page, not the tile.
            auto* info=lv_button_create(t);lv_obj_set_size(info,64,64);lv_obj_align(info,LV_ALIGN_TOP_RIGHT,6,-6);
            lv_obj_set_style_radius(info,LV_RADIUS_CIRCLE,0);lv_obj_set_style_bg_opa(info,LV_OPA_TRANSP,0);
            lv_obj_set_style_bg_opa(info,LV_OPA_50,LV_STATE_PRESSED);lv_obj_set_style_shadow_width(info,0,0);
            lv_obj_set_style_border_width(info,3,0);lv_obj_set_style_border_color(info,lv_color_hex(0x90a4ae),0);
            lv_obj_add_event_cb(info,info_open,LV_EVENT_CLICKED,reinterpret_cast<void*>(static_cast<uintptr_t>(i)));
            auto* glyph=label(info,"i",&lv_font_montserrat_36,0xe0e0e0);lv_obj_center(glyph);
        }
        readings[i]=label(t,"",&lv_font_montserrat_28,0xe0e0e0);
        lv_obj_set_width(readings[i],r.w-40);lv_label_set_long_mode(readings[i],LV_LABEL_LONG_WRAP);
        lv_obj_align(readings[i],LV_ALIGN_BOTTOM_LEFT,0,0);
    }
    for(unsigned i:{motion_tile,power_tile,audio_tile})lv_label_set_text(readings[i],"No data");
    lv_label_set_text(readings[0],"Open");lv_label_set_text(readings[1],"Open");
    info_panel=lv_obj_create(screen);lv_obj_remove_style_all(info_panel);
    lv_obj_set_size(info_panel,home::screen_w,home::screen_h);lv_obj_set_pos(info_panel,0,0);
    lv_obj_set_style_bg_color(info_panel,lv_color_hex(0x101418),0);lv_obj_set_style_bg_opa(info_panel,LV_OPA_COVER,0);
    lv_obj_remove_flag(info_panel,LV_OBJ_FLAG_SCROLLABLE);
    info_title=label(info_panel,"",&lv_font_montserrat_40,0xffffff);lv_obj_set_pos(info_title,home::margin,20);
    auto* close=lv_button_create(info_panel);lv_obj_set_pos(close,1070,14);lv_obj_set_size(close,186,64);
    lv_obj_add_event_cb(close,info_close,LV_EVENT_CLICKED,nullptr);
    auto* close_label=label(close,"Close",&lv_font_montserrat_24,0xffffff);lv_obj_center(close_label);
    info_scroll=lv_obj_create(info_panel);lv_obj_set_pos(info_scroll,home::margin,96);
    lv_obj_set_size(info_scroll,home::screen_w-2*home::margin,home::screen_h-96-home::margin);
    lv_obj_set_style_bg_color(info_scroll,lv_color_hex(0x161c21),0);lv_obj_set_style_border_width(info_scroll,0,0);
    lv_obj_set_style_pad_all(info_scroll,28,0);lv_obj_set_scroll_dir(info_scroll,LV_DIR_VER);
    lv_obj_set_scrollbar_mode(info_scroll,LV_SCROLLBAR_MODE_ACTIVE);
    lv_obj_add_event_cb(info_scroll,info_scrolled,LV_EVENT_SCROLL,nullptr);
    info_text=label(info_scroll,"",&lv_font_montserrat_28,0xe0e0e0);
    lv_obj_set_width(info_text,lv_pct(100));lv_label_set_long_mode(info_text,LV_LABEL_LONG_WRAP);
    lv_obj_set_style_text_line_space(info_text,8,0);
    lv_obj_add_flag(info_panel,LV_OBJ_FLAG_HIDDEN);
    // Diagnostics is the screen underneath; this button returns home from it.
    auto* back=lv_button_create(screen);lv_obj_set_pos(back,1020,20);lv_obj_set_size(back,230,58);
    lv_obj_add_event_cb(back,home_clicked,LV_EVENT_CLICKED,nullptr);
    auto* back_label=lv_label_create(back);lv_label_set_text(back_label,"Home");lv_obj_center(back_label);
    if(auto* indev=lv_indev_get_next(nullptr))lv_indev_add_event_cb(indev,pressed,LV_EVENT_PRESSED,nullptr);
    lv_display_add_event_cb(lv_display_get_default(),refreshed,LV_EVENT_REFR_READY,nullptr);
    lv_timer_create(draw,250,nullptr);
    show_home(false);
}

void home_ui_open() {show_home(true);}

void home_readings(float tilt_degrees,float bus_v,float shunt_a,bool headphones) {
    portENTER_CRITICAL(&readings_lock);
    latest.tilt=tilt_degrees;latest.bus_v=bus_v;latest.shunt_a=shunt_a;latest.headphones=headphones;latest.fresh=true;
    portEXIT_CRITICAL(&readings_lock);
}

void home_returned(const char* from,const char* to) {
    note_nav(from,to?to:lv_obj_has_flag(home_panel,LV_OBJ_FLAG_HIDDEN)?"diagnostics":"home");
}
