#include "investigation.h"
#include "investigation_protocol.h"
#include "investigation_wire.h"
#include "investigation_capture.h"
#include "transport_write.h"
#include "test_storage.h"
#include "diagnostic_events.h"
#include "network.h"
#include "spectrum_display.h"
#include "bsp/m5stack_tab5.h"
#include "esp_transport.h"
#include "esp_transport_tcp.h"
#include "esp_transport_ws.h"
#include "esp_transport_internal.h"
#include "esp_heap_caps.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "mbedtls/base64.h"
#include <atomic>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <memory>
#include <string>
#include <algorithm>
#include <cerrno>
#include <cmath>
#include <initializer_list>
#include <vector>

extern const uint8_t fixture_start[] asm("_binary_guided_ab_fixture_json_start");
extern const uint8_t fixture_end[] asm("_binary_guided_ab_fixture_json_end");
namespace {
lv_obj_t *launch,*panel,*heading,*label,*start_button,*action_button,*action_label,*back_button,*cancel_button,*setup_button;
lv_obj_t *setup_panel,*endpoint_field,*keyboard;
// Instrument view: live spectrum while recording, then A and B overlaid.
lv_obj_t *chart,*legend[3];
lv_chart_series_t* series[3]; // live, A, B
const uint32_t series_colors[3]={0x66bb6a,0x4fc3f7,0xffb74d};
portMUX_TYPE live_lock=portMUX_INITIALIZER_UNLOCKED;
float live_db[spectrum_band_count];
unsigned live_sequence=0,live_drawn=0; // Guarded by live_lock.
QueueHandle_t media_queue,actions;
std::atomic<bool> cancelled{false};
std::atomic<int64_t> cancel_requested_us{0};
bool running=false; // Access only under the display lock.
char endpoint_text[241]{};
char replay_session_text[40]{};
uint64_t now_ms(){return esp_timer_get_time()/1000;}

void open(lv_event_t*) {lv_obj_remove_flag(panel,LV_OBJ_FLAG_HIDDEN);lv_obj_move_foreground(panel);}
void back(lv_event_t*) {if(!running)lv_obj_add_flag(panel,LV_OBJ_FLAG_HIDDEN);}
void open_setup(lv_event_t*) {
    if(running)return;
    lv_obj_remove_flag(setup_panel,LV_OBJ_FLAG_HIDDEN);lv_obj_move_foreground(setup_panel);
}
void close_setup(lv_event_t*) {
    lv_obj_add_flag(keyboard,LV_OBJ_FLAG_HIDDEN);lv_obj_add_flag(setup_panel,LV_OBJ_FLAG_HIDDEN);
    InvestigationEndpoint endpoint;
    if(!running)lv_label_set_text(label,endpoint.parse(lv_textarea_get_text(endpoint_field))?
        "Service address saved for this session. Tap Start.":"Service address invalid. Open Setup and enter ws://Mac-LAN-IP:8765/");
}
void open_wifi(lv_event_t*) {network_ui_open();}

// Capture-loop tap: copy only; the LVGL timer below draws.
void live_tap(const float* db) {
    portENTER_CRITICAL(&live_lock);
    memcpy(live_db,db,sizeof(live_db));++live_sequence;
    portEXIT_CRITICAL(&live_lock);
}
void draw_live(lv_timer_t*) {
    float db[spectrum_band_count];bool fresh;
    portENTER_CRITICAL(&live_lock);
    fresh=live_sequence!=live_drawn;
    if(fresh){memcpy(db,live_db,sizeof(db));live_drawn=live_sequence;}
    portEXIT_CRITICAL(&live_lock);
    if(!fresh)return;
    for(size_t i=0;i<spectrum_band_count;++i)lv_chart_set_value_by_id(chart,series[0],i,spectrum_chart_value(db[i]));
    lv_chart_refresh(chart);
}
void show_series(unsigned index,bool visible) {
    lv_chart_hide_series(chart,series[index],!visible);
    if(visible)lv_obj_remove_flag(legend[index],LV_OBJ_FLAG_HIDDEN);else lv_obj_add_flag(legend[index],LV_OBJ_FLAG_HIDDEN);
}
// Media task: recording A shows only live; recording B shows live over A.
void chart_recording(unsigned index) {
    if(!bsp_display_lock(1000))return;
    lv_chart_set_all_value(chart,series[0],LV_CHART_POINT_NONE);
    show_series(0,true);show_series(1,index==1);show_series(2,false);
    lv_chart_refresh(chart);bsp_display_unlock();
}
void chart_capture(unsigned index,const float* db) {
    if(!bsp_display_lock(1000))return;
    for(size_t i=0;i<spectrum_band_count;++i)lv_chart_set_value_by_id(chart,series[index+1],i,spectrum_chart_value(db[i]));
    show_series(0,false);show_series(index+1,true);
    lv_chart_refresh(chart);bsp_display_unlock();
}
void chart_clear() {
    for(unsigned s=0;s<3;++s){lv_chart_set_all_value(chart,series[s],LV_CHART_POINT_NONE);show_series(s,false);}
    lv_chart_refresh(chart);
}
// Whole-capture average of the measurement slot for the A/B overlay (display
// only; the host's comparison is computed from the uploaded bytes).
bool capture_bands(const InvestigationCapture& c,float* db) {
    struct Scratch {SpectrumWorkspace workspace;float amplitudes[spectrum_max_frames/2+1];};
    std::unique_ptr<Scratch,decltype(&free)> scratch(static_cast<Scratch*>(
        heap_caps_aligned_alloc(16,sizeof(Scratch),MALLOC_CAP_SPIRAM)),free);
    const int64_t started=esp_timer_get_time();SpectrumBands bands;
    const bool ok=scratch && c.bytes && spectrum_bands_pcm16(reinterpret_cast<const int16_t*>(c.bytes),c.size/8,4,0,
        spectrum_max_frames,48000,scratch->workspace,scratch->amplitudes,spectrum_max_frames/2+1,bands);
    if(ok)spectrum_bands_db(bands,db);
    auto* e=diagnostic_event("investigation_capture_spectrum");cJSON_AddBoolToObject(e,"ok",ok);
    cJSON_AddNumberToObject(e,"windows",bands.windows);
    cJSON_AddNumberToObject(e,"duration_us",esp_timer_get_time()-started);diagnostic_emit(e);
    return ok;
}
const char* heading_text(InvestigationProtocol::State s) {
    using S=InvestigationProtocol::State;
    switch(s) {
    case S::Idle:case S::Connecting:return "Connecting";
    case S::ReadyA:return "Step 1: record A";
    case S::RecordingA:return "Recording A";
    case S::Uploading:return "Uploading";
    case S::Waiting:case S::Acknowledging:return "Waiting for guidance";
    case S::Adjust:return "Step 2: move to B";
    case S::ReadyB:return "Step 3: record B";
    case S::RecordingB:return "Recording B (A shown for reference)";
    case S::Complete:return "Comparison: A vs B";
    case S::Cancelled:return "Cancelled";
    case S::Offline:return "Offline";
    default:return "Incomplete";
    }
}
void cancel(lv_event_t*) {
    if(!running)return;
    cancel_requested_us.store(esp_timer_get_time());
    cancelled.store(true);
    lv_label_set_text(label,"Cancelled locally. Waiting for capture/connection cleanup.");
    lv_obj_add_state(action_button,LV_STATE_DISABLED);
}
void action(lv_event_t*) {
    if(!running || cancelled.load())return;
    uint8_t value=1;if(xQueueSend(actions,&value,0)==pdTRUE)lv_obj_add_state(action_button,LV_STATE_DISABLED);
}
void edit_endpoint(lv_event_t*) {
    if(!running)lv_obj_remove_flag(keyboard,LV_OBJ_FLAG_HIDDEN);
}
void set_running(bool value) {
    running=value;
    for(auto* b:{start_button,back_button,setup_button,endpoint_field})
        if(value)lv_obj_add_state(b,LV_STATE_DISABLED);else lv_obj_remove_state(b,LV_STATE_DISABLED);
    if(value)lv_obj_remove_state(cancel_button,LV_STATE_DISABLED);else lv_obj_add_state(cancel_button,LV_STATE_DISABLED);
}
void start(lv_event_t*) {
    if(running)return;
    InvestigationEndpoint endpoint;
    const char* text=lv_textarea_get_text(endpoint_field);
    if(!endpoint.parse(text)){lv_label_set_text(label,"No valid service address. Open Setup: join Wi-Fi and enter ws://Mac-LAN-IP:8765/");return;}
    strcpy(endpoint_text,text);cancel_requested_us.store(0);cancelled.store(false);xQueueReset(actions);
    uint8_t command=4;
    if(xQueueSend(media_queue,&command,0)!=pdTRUE){lv_label_set_text(label,"Media owner busy. Try again.");return;}
    set_running(true);chart_clear();
    lv_label_set_text(heading,"Connecting");
    lv_label_set_text(label,"Connecting to the Mac service...");
}
lv_obj_t* button(lv_obj_t* parent,const char* text,int x,int y,lv_event_cb_t callback) {
    auto* b=lv_button_create(parent);lv_obj_set_pos(b,x,y);lv_obj_set_size(b,220,60);
    lv_obj_add_event_cb(b,callback,LV_EVENT_CLICKED,nullptr);
    auto* l=lv_label_create(b);lv_label_set_text(l,text);lv_obj_center(l);return b;
}
void show(InvestigationProtocol& p,const char* message,const char* button_text=nullptr) {
    if(bsp_display_lock(1000)) {
        // A worker completion must never overwrite a locally visible cancel.
        if(cancelled.load())p.cancel();
        lv_label_set_text(heading,heading_text(p.state()));
        if(p.state()==InvestigationProtocol::State::Cancelled)lv_label_set_text(label,"Cancelled. This session cannot resume. Start a new investigation.");
        else lv_label_set_text(label,message);
        lv_obj_add_state(action_button,LV_STATE_DISABLED);
        if(button_text && !p.terminal()) {
            lv_label_set_text(action_label,button_text);xQueueReset(actions);
            lv_obj_remove_state(action_button,LV_STATE_DISABLED);
        }
        bsp_display_unlock();
    }
    auto* e=diagnostic_event("investigation_state");cJSON_AddStringToObject(e,"state",p.state_name());
    auto* identity=p.envelope("identity");
    cJSON_AddStringToObject(e,"session_id",cJSON_GetObjectItemCaseSensitive(identity,"session_id")->valuestring);
    cJSON_Delete(identity);diagnostic_emit(e);
}

// The pinned TCP writer may return a positive short count. Complete that byte
// range below WS framing, under its original budget; a fresh WS send would
// corrupt the unfinished frame. All handles remain owned by the media worker.
struct TcpCompletion {
    esp_transport_handle_t tcp=nullptr;
    bool failed=false, cancel_notice=false;
};
TcpCompletion& completion(esp_transport_handle_t t) {
    return *static_cast<TcpCompletion*>(esp_transport_get_context_data(t));
}
esp_transport_handle_t parent_tcp(esp_transport_handle_t t) {
    return completion(t).tcp;
}
int complete_write(esp_transport_handle_t t,const char* data,int size,int timeout) {
    auto& state=completion(t);
    if(state.failed)return -1;
    const int result=transport_write_all(data,size,timeout,
        [t](const char* bytes,int count,int budget) {
            int sent=esp_transport_write(parent_tcp(t),bytes,count,budget);
            if(sent>0 && sent<count) {
                auto* e=diagnostic_event("investigation_tcp_short_write");
                cJSON_AddNumberToObject(e,"requested_bytes",count);
                cJSON_AddNumberToObject(e,"sent_bytes",sent);diagnostic_emit(e);
            }
            return sent;
        },now_ms,[&state]{return cancelled.load() && !state.cancel_notice;});
    if(result!=size)state.failed=true;
    return result;
}

class Socket {
public:
    esp_transport_handle_t tcp=nullptr,complete_tcp=nullptr,ws=nullptr;
    TcpCompletion completion_state;
    char* buffer=nullptr;
    std::unique_ptr<InvestigationFrames> frames;
    Socket() {
        buffer=static_cast<char*>(heap_caps_malloc(32769,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
        if(buffer)frames.reset(new InvestigationFrames(buffer));
        tcp=esp_transport_tcp_init();
        if(tcp)complete_tcp=esp_transport_init();
        if(complete_tcp) {
            completion_state.tcp=tcp;
            esp_transport_set_context_data(complete_tcp,&completion_state);
            // Pinned IDF's WS close handler requires the parent's socket getter,
            // and its error capture shares the TCP foundation. Public callbacks
            // alone do not forward these; preserve both before constructing WS.
            complete_tcp->foundation=tcp->foundation;
            complete_tcp->_get_socket=[](esp_transport_handle_t t){return esp_transport_get_socket(parent_tcp(t));};
            esp_transport_set_func(complete_tcp,
                [](esp_transport_handle_t t,const char* host,int port,int timeout){return esp_transport_connect(parent_tcp(t),host,port,timeout);},
                [](esp_transport_handle_t t,char* data,int size,int timeout){return esp_transport_read(parent_tcp(t),data,size,timeout);},
                complete_write,
                [](esp_transport_handle_t t){return esp_transport_close(parent_tcp(t));},
                [](esp_transport_handle_t t,int timeout){return esp_transport_poll_read(parent_tcp(t),timeout);},
                [](esp_transport_handle_t t,int timeout){return esp_transport_poll_write(parent_tcp(t),timeout);},
                [](esp_transport_handle_t){return ESP_OK;});
            esp_transport_set_parent_transport_func(complete_tcp,parent_tcp);
            ws=esp_transport_ws_init(complete_tcp);
        }
    }
    ~Socket() {if(ws){esp_transport_close(ws);esp_transport_destroy(ws);}if(complete_tcp)esp_transport_destroy(complete_tcp);if(tcp)esp_transport_destroy(tcp);free(buffer);}
    bool connect(const InvestigationEndpoint& e) {
        if(cancelled.load() || !ws || !buffer)return false;
        esp_transport_ws_set_path(ws,e.path);
        return esp_transport_connect(ws,e.host,e.port,3000)==0;
    }
    bool send(cJSON* object) {
        if(!object)return false;
        auto* type=cJSON_GetObjectItemCaseSensitive(object,"type");
        const std::string kind=cJSON_IsString(type)?type->valuestring:"unknown";
        char* data=cJSON_PrintUnformatted(object);cJSON_Delete(object);
        if(!data)return false;
        size_t n=strlen(data);
        int64_t started=esp_timer_get_time();errno=0;
        // A clean connection may notify a local cancel. Never append another
        // frame after any failed/partial write, including cancellation mid-frame.
        completion_state.cancel_notice=kind=="cancel";
        int sent=n<=32768?esp_transport_ws_send_raw(ws,static_cast<ws_transport_opcodes_t>(0x81),data,n,2000):-1;
        completion_state.cancel_notice=false;
        int error=errno;bool ok=sent==static_cast<int>(n);
        if(!ok || kind!="capture_chunk") {
            auto* e=diagnostic_event("investigation_transport");
            cJSON_AddStringToObject(e,"message_type",kind.c_str());cJSON_AddNumberToObject(e,"requested_bytes",n);
            cJSON_AddNumberToObject(e,"sent_bytes",sent);cJSON_AddNumberToObject(e,"errno",error);
            cJSON_AddNumberToObject(e,"duration_us",esp_timer_get_time()-started);diagnostic_emit(e);
        }
        cJSON_free(data);return ok;
    }
    // 0 idle, 1 complete message, -1 protocol/connection error. No network
    // operation runs under the display lock. Ping/pong handled by pinned IDF.
    int poll() {
        int ready=esp_transport_poll_read(ws,20);if(ready<=0)return ready;
        char chunk[1024];int n=esp_transport_read(ws,chunk,sizeof(chunk),1000);
        if(n<0)return -1;
        if(!n)return 0;
        return frames->append(esp_transport_ws_get_read_opcode(ws),esp_transport_ws_get_read_payload_len(ws),
                              esp_transport_ws_get_fin_flag(ws),chunk,n);
    }
    void consumed(){frames->reset();}
};

bool active(InvestigationProtocol& p) {
    if(cancelled.load())p.cancel();
    p.tick(now_ms());return !p.terminal();
}
bool wait_reply(Socket& s,InvestigationProtocol& p) {
    while(active(p)) {
        int result=s.poll();
        if(result<0){p.disconnect();return false;}
        if(result==1) {
            // Recheck cancel after a blocking read, before consuming a reply.
            if(!active(p))return false;
            bool ok=p.receive(s.buffer,now_ms());s.consumed();
            if(!ok)p.fail();
            return ok;
        }
    }
    return false;
}
bool wait_action(Socket& s,InvestigationProtocol& p) {
    uint8_t command;
    while(active(p)) {
        int result=s.poll();
        if(result<0){p.disconnect();return false;}
        if(result==1){s.consumed();p.fail();return false;}
        if(xQueueReceive(actions,&command,0)==pdTRUE)return active(p);
    }
    return false;
}
bool capture_ack(Socket& s,InvestigationProtocol& p,const char* id,const char* stage,const char* sha=nullptr) {
    const uint64_t deadline=now_ms()+5000;
    while(active(p) && now_ms()<deadline) {
        int result=s.poll();if(result<0){p.disconnect();return false;}
        if(result==1) {
            auto* o=InvestigationProtocol::parse(s.buffer);s.consumed();
            auto equal=[&](const char* key,const char* value) {
                auto* f=cJSON_GetObjectItemCaseSensitive(o,key);return cJSON_IsString(f) && !strcmp(f->valuestring,value);
            };
            bool ok=active(p) && o && p.same_session(o) && cJSON_GetArraySize(o)==(sha?7:6) &&
                equal("type","capture_ack") && equal("capture_id",id) && equal("stage",stage) && (!sha || equal("sha256",sha));
            cJSON_Delete(o);if(!ok)p.fail();
            return ok;
        }
    }
    p.fail();return false;
}
bool upload(Socket& s,InvestigationProtocol& p,const InvestigationCapture& c,unsigned index) {
    const char* id=p.capture_id(index);auto* o=p.envelope("capture_start");
    cJSON_AddItemToObject(o,"metadata",cJSON_Duplicate(c.metadata,true));
    if(!active(p)){cJSON_Delete(o);return false;}
    if(!s.send(o) || !capture_ack(s,p,id,"start"))return false;
    // One reusable base64 scratch buffer; at most 4096 raw bytes per message.
    auto* encoded=static_cast<unsigned char*>(malloc(5465));if(!encoded)return false;
    bool ok=true;
    for(size_t offset=0;ok && offset<c.size;offset+=4096) {
        if(!active(p)){ok=false;break;}
        size_t count=std::min(size_t(4096),c.size-offset),written=0;
        ok=mbedtls_base64_encode(encoded,5465,&written,c.bytes+offset,count)==0;
        if(!ok)break;
        encoded[written]=0;
        o=p.envelope("capture_chunk");cJSON_AddStringToObject(o,"capture_id",id);
        cJSON_AddNumberToObject(o,"offset",offset);cJSON_AddStringToObject(o,"data",reinterpret_cast<char*>(encoded));
        ok=s.send(o);
    }
    free(encoded);if(!ok)return false;
    const char* sha=cJSON_GetObjectItemCaseSensitive(c.metadata,"sha256")->valuestring;
    o=p.envelope("capture_end");cJSON_AddStringToObject(o,"capture_id",id);cJSON_AddStringToObject(o,"sha256",sha);
    if(!active(p)){cJSON_Delete(o);return false;}
    return s.send(o) && capture_ack(s,p,id,"complete",sha);
}

// Device-side geometry check on LVGL's resolved rectangles: every control
// inside its panel and no two main-flow controls overlapping.
bool layout_ok(lv_obj_t* parent,std::initializer_list<lv_obj_t*> objects) {
    lv_area_t outer{};lv_obj_get_coords(parent,&outer);
    std::vector<lv_area_t> areas;
    for(auto* o:objects) {
        lv_area_t a{};lv_obj_get_coords(o,&a);
        if(a.x1<outer.x1 || a.y1<outer.y1 || a.x2>outer.x2 || a.y2>outer.y2)return false;
        for(auto& b:areas)if(a.x1<=b.x2 && b.x1<=a.x2 && a.y1<=b.y2 && b.y1<=a.y2)return false;
        areas.push_back(a);
    }
    return true;
}
lv_obj_t* text(lv_obj_t* parent,const char* value,int x,int y,const lv_font_t* font,uint32_t color=0xffffff) {
    auto* l=lv_label_create(parent);lv_label_set_text(l,value);lv_obj_set_pos(l,x,y);
    lv_obj_set_style_text_font(l,font,0);lv_obj_set_style_text_color(l,lv_color_hex(color),0);return l;
}
}

void investigation_ui_init(lv_obj_t* screen,QueueHandle_t media_commands) {
    media_queue=media_commands;actions=xQueueCreate(1,sizeof(uint8_t));configASSERT(actions);
    launch=button(screen,"Guided A/B",30,220,open);lv_obj_add_state(launch,LV_STATE_DISABLED);
    panel=lv_obj_create(screen);lv_obj_set_size(panel,1220,680);lv_obj_center(panel);
    lv_obj_set_style_bg_color(panel,lv_color_hex(0x101418),0);lv_obj_remove_flag(panel,LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(panel,LV_OBJ_FLAG_HIDDEN);
    heading=text(panel,"Steady sound A/B",0,0,&lv_font_montserrat_28);
    const char* names[3]={"Live","A","B"};
    for(unsigned s=0;s<3;++s)legend[s]=text(panel,names[s],900+s*95,6,&lv_font_montserrat_24,series_colors[s]);

    // 48 log bands, 50 Hz-20 kHz; 0..100 maps floor..ceiling dB.
    constexpr int chart_x=80,chart_y=50,chart_w=1090,chart_h=270;
    chart=lv_chart_create(panel);lv_obj_set_pos(chart,chart_x,chart_y);lv_obj_set_size(chart,chart_w,chart_h);
    lv_chart_set_type(chart,LV_CHART_TYPE_LINE);lv_chart_set_point_count(chart,spectrum_band_count);
    lv_chart_set_range(chart,LV_CHART_AXIS_PRIMARY_Y,0,100);lv_chart_set_div_line_count(chart,5,0);
    lv_obj_set_style_pad_all(chart,0,0);lv_obj_set_style_bg_color(chart,lv_color_hex(0x000000),0);
    lv_obj_set_style_border_color(chart,lv_color_hex(0x37474f),0);
    lv_obj_set_style_line_color(chart,lv_color_hex(0x263238),LV_PART_MAIN);
    lv_obj_set_style_line_width(chart,3,LV_PART_ITEMS);lv_obj_set_style_size(chart,0,0,LV_PART_INDICATOR);
    for(unsigned s=0;s<3;++s)series[s]=lv_chart_add_series(chart,lv_color_hex(series_colors[s]),LV_CHART_AXIS_PRIMARY_Y);
    chart_clear();
    for(int step=0;step<5;++step) {
        char value[16];snprintf(value,sizeof(value),"%d",static_cast<int>(spectrum_ceiling_db)-20*step);
        text(panel,value,0,chart_y+step*(chart_h-1)/4-10,&lv_font_montserrat_18,0x90a4ae);
    }
    text(panel,"dB",0,chart_y+chart_h+6,&lv_font_montserrat_18,0x90a4ae);
    for(float hz:{100.0f,1000.0f,10000.0f}) {
        const float band=std::log(hz/spectrum_band_low_hz)/std::log(spectrum_band_high_hz/spectrum_band_low_hz)*spectrum_band_count-0.5f;
        const int x=chart_x+static_cast<int>(band/(spectrum_band_count-1)*chart_w);
        text(panel,hz<1000?"100 Hz":hz<10000?"1 kHz":"10 kHz",x-30,chart_y+chart_h+6,&lv_font_montserrat_18,0x90a4ae);
    }

    auto* transcript=lv_obj_create(panel);lv_obj_set_pos(transcript,0,355);lv_obj_set_size(transcript,1170,190);
    label=lv_label_create(transcript);lv_obj_set_width(label,1120);
    lv_obj_set_style_text_font(label,&lv_font_montserrat_22,0);
    lv_label_set_long_mode(label,LV_LABEL_LONG_WRAP);
    lv_label_set_text(label,"Steady sound A/B test. Record at A, move, record at B, then compare.\nKeep the source level and device orientation fixed. Tap Start.");
    start_button=button(panel,"Start",0,560,start);
    action_button=button(panel,"Record A",235,560,action);action_label=lv_obj_get_child(action_button,0);
    lv_obj_add_state(action_button,LV_STATE_DISABLED);
    cancel_button=button(panel,"Cancel",470,560,cancel);lv_obj_add_state(cancel_button,LV_STATE_DISABLED);
    setup_button=button(panel,"Setup",705,560,open_setup);
    back_button=button(panel,"Back",940,560,back);
    lv_timer_create(draw_live,60,nullptr);

    // Setup stays off the main flow: service address, Wi-Fi and keyboard.
    setup_panel=lv_obj_create(screen);lv_obj_set_size(setup_panel,1220,680);lv_obj_center(setup_panel);
    lv_obj_add_flag(setup_panel,LV_OBJ_FLAG_HIDDEN);
    text(setup_panel,"Setup",0,0,&lv_font_montserrat_28,0x000000);
    auto* done=button(setup_panel,"Done",955,0,close_setup);
    text(setup_panel,"Mac service address (loaded from SD at boot)",0,75,&lv_font_montserrat_20,0x000000);
    endpoint_field=lv_textarea_create(setup_panel);lv_obj_set_pos(endpoint_field,0,110);lv_obj_set_size(endpoint_field,920,60);
    lv_textarea_set_one_line(endpoint_field,true);lv_textarea_set_max_length(endpoint_field,240);
    lv_textarea_set_placeholder_text(endpoint_field,"ws://Mac-LAN-IP:8765/");
    lv_textarea_set_text(endpoint_field,CONFIG_TRICORDER_INVESTIGATION_ENDPOINT);
    auto* wifi=button(setup_panel,"Wi-Fi setup",955,110,open_wifi);
    keyboard=lv_keyboard_create(setup_panel);lv_obj_set_size(keyboard,1160,300);lv_obj_align(keyboard,LV_ALIGN_BOTTOM_MID,0,0);
    lv_keyboard_set_textarea(keyboard,endpoint_field);lv_obj_add_flag(keyboard,LV_OBJ_FLAG_HIDDEN);
    lv_obj_add_event_cb(endpoint_field,edit_endpoint,LV_EVENT_FOCUSED,nullptr);

    for(auto* p:{panel,setup_panel,keyboard})lv_obj_remove_flag(p,LV_OBJ_FLAG_HIDDEN);
    lv_obj_update_layout(screen);
    diagnostic_check("investigation_keyboard_layout",layout_ok(setup_panel,{done,endpoint_field,wifi,keyboard})?"pass":"fail",
                     "Resolved setup controls and keyboard stay inside the setup panel without overlap.");
    diagnostic_check("investigation_layout",layout_ok(panel,{heading,chart,transcript,start_button,action_button,cancel_button,setup_button,back_button})?"pass":"fail",
                     "Resolved A/B heading, spectrum, guidance and buttons stay inside the panel without overlap.");
    for(auto* p:{panel,setup_panel,keyboard})lv_obj_add_flag(p,LV_OBJ_FLAG_HIDDEN);
}
void investigation_ui_open() {open(nullptr);}
void investigation_ui_enable(bool enabled) {
    if(enabled)lv_obj_remove_state(launch,LV_STATE_DISABLED);else lv_obj_add_state(launch,LV_STATE_DISABLED);
}
static void run_investigation(const char* boot,const char* replay=nullptr) {
    InvestigationEndpoint endpoint;char session[40];
    if(replay)strcpy(session,replay);
    else snprintf(session,sizeof(session),"ab-%08lx%08lx%08lx%08lx",static_cast<unsigned long>(esp_random()),
             static_cast<unsigned long>(esp_random()),static_cast<unsigned long>(esp_random()),static_cast<unsigned long>(esp_random()));
    // Heap-owned reducer keeps fixed text/identity buffers off the 8 KiB main stack.
    auto p=std::make_unique<InvestigationProtocol>(boot,session);p->ask(now_ms());
    Socket socket;
    std::unique_ptr<cJSON,decltype(&cJSON_Delete)> fixture(
        cJSON_ParseWithLength(reinterpret_cast<const char*>(fixture_start),fixture_end-fixture_start),cJSON_Delete);
    auto fixture_text=[&](const char* key) {
        auto* value=cJSON_GetObjectItemCaseSensitive(fixture.get(),key);
        return cJSON_IsString(value)?value->valuestring:"";
    };
    const std::string question=fixture_text("question"),placement_a=fixture_text("placement_a"),placement_b=fixture_text("placement_b");
    if(question.empty() || placement_a.empty() || placement_b.empty())p->fail();
    if(!active(*p) || !endpoint.parse(endpoint_text) || !socket.connect(endpoint))p->disconnect();
    else if(active(*p)) {
        auto* hello=p->envelope("hello");
        if(replay)cJSON_AddBoolToObject(hello,"replay",true);
        cJSON_AddItemToObject(hello,"fixture",cJSON_Duplicate(fixture.get(),true));
        if(!socket.send(hello))p->disconnect();else wait_reply(socket,*p);
    }
    for(unsigned index=0;index<2 && active(*p);++index) {
        const std::string prompt=question+"\n\n"+(index==0?placement_a:placement_b)+
            "\nStop moving before recording. Three seconds; device speaker stays silent.";
        show(*p,replay?"SD REPLAY: loading original recordings. No new sensor acquisition.":prompt.c_str(),replay?nullptr:index==0?"Record A":"Record B");
        if((!replay && !wait_action(socket,*p)) || !p->start_capture())break;
        if(!replay)show(*p,index==0?"Settling 0.5s, then recording A / 3s\nHold still; speaker silent.":"Settling 0.5s, then recording B / 3s\nHold still; speaker silent.");
        {
            InvestigationCapture capture;char id[48];snprintf(id,sizeof(id),"%s-%c",session,index?'b':'a');
            if(!replay)chart_recording(index);
            const bool loaded=replay?test_storage_load_capture(id,capture):investigation_capture(boot,session,id,cancelled,capture,live_tap);
            if(!loaded || !active(*p) ||
               !p->captured(capture.metadata,capture.measurement,now_ms())){p->fail();break;}
            float db[spectrum_band_count];
            if(capture_bands(capture,db))chart_capture(index,db);
            if(replay)show(*p,"SD REPLAY: uploading original verified recording...");
            else {
                show(*p,"Saving the verified recording to SD...");
                const bool saved=test_storage_archive(capture.bytes,capture.size,capture.metadata);
                show(*p,saved?"Saved to SD. Uploading the verified recording...":"SD save unavailable. Uploading the verified recording...");
            }
            if(!upload(socket,*p,capture,index)){p->fail();break;}
        } // Free raw PCM only after the service's matching completion/hash ACK.
        if(!active(*p))break;
        if(!socket.send(p->turn(now_ms()))){p->disconnect();break;}
        show(*p,"Waiting for evidence-linked guidance...\nCancel is available.");
        if(!wait_reply(socket,*p))break;
        if(!active(*p))break;
        if(!socket.send(p->ack())){p->disconnect();break;}
        if(!wait_reply(socket,*p))break;
        if(index==0) {
            show(*p,p->text(),replay?nullptr:"Confirm position B");
            if((!replay && !wait_action(socket,*p)) || !p->adjust(replay?"SD replay of original recorded A/B adjustment; no new movement":("Moved to "+placement_b+"; same source level").c_str()))break;
        }
    }
    if(cancelled.load()) {
        p->cancel();
        auto* e=diagnostic_event("investigation_cancel");
        cJSON_AddStringToObject(e,"session_id",session);
        cJSON_AddNumberToObject(e,"requested_device_us",cancel_requested_us.load());
        cJSON_AddNumberToObject(e,"owner_stopped_device_us",esp_timer_get_time());
        diagnostic_emit(e);
        if(socket.ws)socket.send(p->envelope("cancel"));
    }
    if(!p->terminal())p->fail();
    const char* final_text=p->state()==InvestigationProtocol::State::Complete?p->text():
        p->state()==InvestigationProtocol::State::Offline?"Offline. Check Wi-Fi and the Mac service. Start a new investigation; this session cannot resume.":
        "Incomplete. No valid comparison. Check the retained run evidence, then start a new investigation.";
    const std::string displayed=replay?std::string("SD REPLAY (no new acquisition)\n")+final_text:final_text;
    show(*p,displayed.c_str());
    if(bsp_display_lock(1000)) {
        set_running(false);show_series(0,false);
        bsp_display_unlock();
    }
}

void investigation_run(const char* boot) {run_investigation(boot);}
bool investigation_request_replay(const char* session) {
    if(!investigation_replay_session(session) || !media_queue || !bsp_display_lock(1000))return false;
    InvestigationEndpoint endpoint;bool ok=!running && endpoint.parse(lv_textarea_get_text(endpoint_field));
    if(ok) {
        strcpy(endpoint_text,lv_textarea_get_text(endpoint_field));strcpy(replay_session_text,session);
        cancel_requested_us.store(0);cancelled.store(false);xQueueReset(actions);
        uint8_t command=5;ok=xQueueSend(media_queue,&command,0)==pdTRUE;
        if(ok) {
            set_running(true);chart_clear();lv_obj_add_flag(setup_panel,LV_OBJ_FLAG_HIDDEN);
            lv_obj_remove_flag(panel,LV_OBJ_FLAG_HIDDEN);lv_obj_move_foreground(panel);
            lv_label_set_text(label,"SD REPLAY: checking saved recording identity...");
        }
    }
    bsp_display_unlock();return ok;
}
void investigation_run_replay() {
    std::string boot;bool valid=false;
    {
        InvestigationCapture first;
        if(test_storage_load_capture((std::string(replay_session_text)+"-a").c_str(),first)) {
            auto* b=cJSON_GetObjectItemCaseSensitive(first.metadata,"boot_id");
            auto* s=cJSON_GetObjectItemCaseSensitive(first.metadata,"session_id");
            valid=cJSON_IsString(b) && cJSON_IsString(s) && !strcmp(s->valuestring,replay_session_text);
            if(valid)boot=b->valuestring;
        }
    }
    auto* e=diagnostic_event("investigation_replay");cJSON_AddBoolToObject(e,"source_valid",valid);
    cJSON_AddStringToObject(e,"source_session_id",replay_session_text);
    cJSON_AddStringToObject(e,"source_boot_id",boot.c_str());diagnostic_emit(e);
    if(valid){run_investigation(boot.c_str(),replay_session_text);return;}
    if(bsp_display_lock(1000)) {
        set_running(false);lv_label_set_text(label,"SD REPLAY failed: saved recording missing or invalid.");
        bsp_display_unlock();
    }
}

void investigation_set_endpoint(const char* endpoint) {
    if(bsp_display_lock(1000)) {
        if(!running)lv_textarea_set_text(endpoint_field,endpoint);
        bsp_display_unlock();
    }
}
