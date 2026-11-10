#include "setup.h"
#include "home.h"
#include "home_model.h"
#include "network.h"
#include "service_wire.h"
#include <initializer_list>
#include "freertos/FreeRTOS.h"
#include <cstdio>
#include <cstring>

namespace {
portMUX_TYPE endpoint_lock=portMUX_INITIALIZER_UNLOCKED;
char endpoint[241]=CONFIG_TRICORDER_INVESTIGATION_ENDPOINT; // endpoint_lock
EndpointSource source=EndpointSource::Default;unsigned version=1; // endpoint_lock
// LVGL task only.
lv_obj_t *panel,*network_label,*audio_label,*address_field,*address_label,*caption_label,*mode_label,*keyboard;
unsigned shown_version=0;

struct Stored {char text[sizeof(endpoint)];EndpointSource source;unsigned version;};
Stored stored() {
    Stored s;
    portENTER_CRITICAL(&endpoint_lock);memcpy(s.text,endpoint,sizeof(endpoint));s.source=source;s.version=version;
    portEXIT_CRITICAL(&endpoint_lock);
    return s;
}
bool waiting_for_mac() {return network_access_point() && !network_peer_ipv4();}
const char* caption(const Stored& s) {
    if(waiting_for_mac())return "Set when the Mac joins the hotspot";
    ServiceEndpoint parsed;
    if(!parsed.parse(s.text))return "Not a valid address; enter ws://Mac-IP:8765/";
    switch(s.source) {
    case EndpointSource::Sd:return "From the SD card at boot";
    case EndpointSource::Hotspot:
        return network_access_point()?"Set when the Mac joined the hotspot":"Left from the hotspot; enter the Mac's address on this network";
    case EndpointSource::Typed:return "Entered here; lasts until restart";
    default:return "Built-in default; the SD card has none";
    }
}
const char* mode_copy(bool hotspot) {
    if(hotspot)return "Hotspot mode: the Mac joins the device's own network, named above. The service address fills in by itself. "
        "The Mac has no Internet while joined.\n\n"
        "The other way is Wi-Fi mode: tap Wi-Fi setup to put the device on a network the Mac is also on.";
    return network_hotspot_saved()?
        "Wi-Fi mode: the device and the Mac are on the same network. Enter the Mac's address above. "
        "Cafe and guest networks usually block this; a phone hotspot works.\n\n"
        "The other way is hotspot mode, where the Mac joins the device's own network: tap Wi-Fi setup, then Back to hotspot.":
        "Wi-Fi mode: the device and the Mac are on the same network. Enter the Mac's address above. "
        "Cafe and guest networks usually block this; a phone hotspot works.\n\n"
        "The other way is hotspot mode, where the Mac joins the device's own network. It is set up over USB.";
}
bool editing() {return !lv_obj_has_flag(keyboard,LV_OBJ_FLAG_HIDDEN);}
void refresh(lv_timer_t*) {
    if(lv_obj_has_flag(panel,LV_OBJ_FLAG_HIDDEN))return;
    char text[96],ssid[33];
    const bool hotspot=network_access_point();
    network_access_point_name(ssid,sizeof(ssid));
    home::setup_network_text(network_ipv4(),network_peer_ipv4(),hotspot,ssid,text,sizeof(text));
    lv_label_set_text(network_label,text);
    const int route=home_audio_route();
    lv_label_set_text(audio_label,route<0?"No reading yet":route?"Headphones":"Speaker");
    // Hotspot mode: the address follows the Mac's lease, so it is shown, not edited.
    if(hotspot && editing())lv_obj_add_flag(keyboard,LV_OBJ_FLAG_HIDDEN);
    if(hotspot){lv_obj_add_flag(address_field,LV_OBJ_FLAG_HIDDEN);lv_obj_remove_flag(address_label,LV_OBJ_FLAG_HIDDEN);}
    else {lv_obj_remove_flag(address_field,LV_OBJ_FLAG_HIDDEN);lv_obj_add_flag(address_label,LV_OBJ_FLAG_HIDDEN);}
    const auto s=stored();
    lv_label_set_text(address_label,waiting_for_mac()?"None yet":s.text);
    if(!editing() && s.version!=shown_version){lv_textarea_set_text(address_field,s.text);shown_version=s.version;}
    lv_label_set_text(caption_label,caption(s));
    lv_label_set_text_static(mode_label,mode_copy(hotspot));
}
void commit() {
    if(!editing())return;
    lv_obj_add_flag(keyboard,LV_OBJ_FLAG_HIDDEN);
    const char* typed=lv_textarea_get_text(address_field);
    if(strcmp(typed,stored().text))setup_set_endpoint(typed,EndpointSource::Typed);
    refresh(nullptr);
}
void field_event(lv_event_t* ev) {
    const auto code=lv_event_get_code(ev);
    if(code==LV_EVENT_FOCUSED || code==LV_EVENT_CLICKED)lv_obj_remove_flag(keyboard,LV_OBJ_FLAG_HIDDEN);
    else if(code==LV_EVENT_READY)commit();
    else if(code==LV_EVENT_CANCEL){lv_obj_add_flag(keyboard,LV_OBJ_FLAG_HIDDEN);shown_version=0;refresh(nullptr);}
}
void done(lv_event_t*) {
    commit();lv_obj_add_flag(panel,LV_OBJ_FLAG_HIDDEN);home_returned("setup");
}
void wifi(lv_event_t*) {commit();network_ui_open();}
lv_obj_t* text(lv_obj_t* parent,const char* value,int x,int y,const lv_font_t* font,uint32_t color) {
    auto* l=lv_label_create(parent);lv_label_set_text(l,value);lv_obj_set_pos(l,x,y);
    lv_obj_set_style_text_font(l,font,0);lv_obj_set_style_text_color(l,lv_color_hex(color),0);return l;
}
void button(lv_obj_t* parent,const char* value,int x,int w,lv_event_cb_t callback) {
    auto* b=lv_button_create(parent);lv_obj_set_pos(b,x,14);lv_obj_set_size(b,w,64);
    lv_obj_add_event_cb(b,callback,LV_EVENT_CLICKED,nullptr);
    auto* l=lv_label_create(b);lv_label_set_text(l,value);lv_obj_set_style_text_font(l,&lv_font_montserrat_28,0);lv_obj_center(l);
}
}

void setup_ui_init(lv_obj_t* screen) {
    panel=lv_obj_create(screen);lv_obj_remove_style_all(panel);lv_obj_set_size(panel,1280,720);lv_obj_set_pos(panel,0,0);
    lv_obj_set_style_bg_color(panel,lv_color_hex(0x101418),0);lv_obj_set_style_bg_opa(panel,LV_OPA_COVER,0);
    lv_obj_remove_flag(panel,LV_OBJ_FLAG_SCROLLABLE);
    text(panel,"Setup",24,20,&lv_font_montserrat_40,0xffffff);
    button(panel,"Wi-Fi setup",842,220,wifi);
    button(panel,"Done",1076,180,done);

    auto* card=lv_obj_create(panel);lv_obj_set_pos(card,24,96);lv_obj_set_size(card,1232,296);
    lv_obj_set_style_bg_color(card,lv_color_hex(0x161c21),0);lv_obj_set_style_border_width(card,0,0);
    lv_obj_remove_flag(card,LV_OBJ_FLAG_SCROLLABLE);
    constexpr int label_x=48,value_x=320,value_w=912;
    text(panel,"Network",label_x,116,&lv_font_montserrat_28,0x90a4ae);
    network_label=text(panel,"",value_x,112,&lv_font_montserrat_32,0xffffff);
    lv_obj_set_width(network_label,value_w);lv_label_set_long_mode(network_label,LV_LABEL_LONG_WRAP);
    text(panel,"Audio out",label_x,216,&lv_font_montserrat_28,0x90a4ae);
    audio_label=text(panel,"",value_x,212,&lv_font_montserrat_32,0xffffff);
    text(panel,"Mac service",label_x,282,&lv_font_montserrat_28,0x90a4ae);
    address_label=text(panel,"",value_x,278,&lv_font_montserrat_32,0xffffff);
    lv_obj_set_width(address_label,value_w);lv_label_set_long_mode(address_label,LV_LABEL_LONG_DOT);
    address_field=lv_textarea_create(panel);lv_obj_set_pos(address_field,value_x,264);lv_obj_set_size(address_field,value_w,68);
    lv_obj_set_style_text_font(address_field,&lv_font_montserrat_28,0);
    lv_textarea_set_one_line(address_field,true);lv_textarea_set_max_length(address_field,sizeof(endpoint)-1);
    lv_textarea_set_placeholder_text(address_field,"ws://Mac-IP:8765/");
    for(auto code:{LV_EVENT_FOCUSED,LV_EVENT_CLICKED,LV_EVENT_READY,LV_EVENT_CANCEL})lv_obj_add_event_cb(address_field,field_event,code,nullptr);
    caption_label=text(panel,"",value_x,342,&lv_font_montserrat_28,0x4fc3f7);
    lv_obj_set_width(caption_label,value_w);lv_label_set_long_mode(caption_label,LV_LABEL_LONG_DOT);

    // Created before the keyboard, which covers it while the address is edited.
    mode_label=text(panel,"",label_x,416,&lv_font_montserrat_28,0xcfd8dc);
    lv_obj_set_width(mode_label,1184);lv_label_set_long_mode(mode_label,LV_LABEL_LONG_WRAP);

    // A new keyboard is aligned to the bottom, so a plain position would push it off the screen.
    keyboard=lv_keyboard_create(panel);lv_obj_align(keyboard,LV_ALIGN_TOP_LEFT,24,404);lv_obj_set_size(keyboard,1232,308);
    lv_obj_set_style_text_font(keyboard,&lv_font_montserrat_28,LV_PART_ITEMS);
    lv_keyboard_set_textarea(keyboard,address_field);lv_obj_add_flag(keyboard,LV_OBJ_FLAG_HIDDEN);
    lv_timer_create(refresh,1000,nullptr);
    lv_obj_add_flag(panel,LV_OBJ_FLAG_HIDDEN);
}

void setup_open() {
    lv_obj_remove_flag(panel,LV_OBJ_FLAG_HIDDEN);lv_obj_move_foreground(panel);refresh(nullptr);
}

void setup_set_endpoint(const char* value,EndpointSource from) {
    portENTER_CRITICAL(&endpoint_lock);
    strlcpy(endpoint,value,sizeof(endpoint));source=from;++version;
    portEXIT_CRITICAL(&endpoint_lock);
}

void setup_endpoint(char* out,size_t size) {
    if(waiting_for_mac()){if(size)out[0]=0;return;}
    portENTER_CRITICAL(&endpoint_lock);strlcpy(out,endpoint,size);portEXIT_CRITICAL(&endpoint_lock);
}
