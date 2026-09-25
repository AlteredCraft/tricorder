#include "investigation.h"
#include "investigation_protocol.h"
#include "investigation_wire.h"
#include "investigation_capture.h"
#include "transport_write.h"
#include "speech_stream.h"
#include "speech_receive.h"
#include "ui_pulse.h"
#include "audio_devices.h"
#include "test_storage.h"
#include "diagnostic_events.h"
#include "network.h"
#include "spectrum_display.h"
#include "steadiness.h"
#include "imu_checked.h"
#include "media.h"
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
// Spoken ask: Ask/Stop/Retry beside Record A/Use, and a live input level while listening.
lv_obj_t *ask_button,*ask_label,*level_bar;
std::atomic<bool> listening{false},stop_question{false};
// Spoken comparison at the end: Cancel stops the speech, not the finished session.
std::atomic<bool> final_speech{false},stop_speech{false};
float live_level=-120;bool level_fresh=false; // Guarded by live_lock.
lv_obj_t *setup_panel,*endpoint_field,*keyboard;
// Instrument view: live spectrum while recording, then A and B overlaid.
lv_obj_t *chart,*legend[4];
lv_chart_series_t* series[4]; // live, A, B, A again
// Context photo (camera, once per session) and IMU steadiness before captures.
constexpr unsigned context_width=320,context_height=180;
lv_obj_t *context_image,*context_caption,*steady_label;
uint16_t* context_pixels=nullptr;
lv_image_dsc_t context_dsc{};
SteadinessReading steady_reading;
bool steady_fresh=false; // Guarded by live_lock.
const uint32_t series_colors[4]={0x66bb6a,0x4fc3f7,0xffb74d,0xce93d8};
portMUX_TYPE live_lock=portMUX_INITIALIZER_UNLOCKED;
float live_db[spectrum_band_count];
UiPulse ui_pulse; // display lock: probe timer, session reset and report
// Touch-down time of the last button press (G-0001.04 C2 touch-to-submit). Console
// taps send CLICKED only, so they leave this unchanged.
std::atomic<int64_t> pressed_us{0};
// Diagnostic switches over USB (TRICORDER_SET), for fault attribution only; both on by default.
std::atomic<bool> sd_archive_enabled{true},context_photo_enabled{true};
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
// Question recorder tap (media task): copy only; the LVGL timer below draws.
void level_tap(float dbfs) {
    portENTER_CRITICAL(&live_lock);live_level=dbfs;level_fresh=true;portEXIT_CRITICAL(&live_lock);
}
void draw_steadiness(const SteadinessReading& r) {
    char text[48];uint32_t color=0x90a4ae;
    if(r.state==SteadinessReading::Steady){snprintf(text,sizeof(text),"Steady  %.1f deg/s",r.peak_dps);color=0x66bb6a;}
    else if(r.state==SteadinessReading::Moving){snprintf(text,sizeof(text),"Hold still  %.0f deg/s",r.peak_dps);color=0xffb74d;}
    else snprintf(text,sizeof(text),"Motion: no data");
    lv_label_set_text(steady_label,text);lv_obj_set_style_text_color(steady_label,lv_color_hex(color),0);
}
void draw_live(lv_timer_t*) {
    float db[spectrum_band_count];bool fresh;SteadinessReading reading;bool steady;float level;bool leveled;
    portENTER_CRITICAL(&live_lock);
    fresh=live_sequence!=live_drawn;
    if(fresh){memcpy(db,live_db,sizeof(db));live_drawn=live_sequence;}
    steady=steady_fresh;reading=steady_reading;steady_fresh=false;
    leveled=level_fresh;level=live_level;level_fresh=false;
    portEXIT_CRITICAL(&live_lock);
    if(steady)draw_steadiness(reading);
    // -60..0 dBFS fills the meter.
    if(leveled)lv_bar_set_value(level_bar,static_cast<int32_t>(std::clamp((level+60.0f)*100.0f/60.0f,0.0f,100.0f)),LV_ANIM_OFF);
    if(!fresh)return;
    for(size_t i=0;i<spectrum_band_count;++i)lv_chart_set_value_by_id(chart,series[0],i,spectrum_chart_value(db[i]));
    lv_chart_refresh(chart);
}
void show_series(unsigned index,bool visible) {
    lv_chart_hide_series(chart,series[index],!visible);
    if(visible)lv_obj_remove_flag(legend[index],LV_OBJ_FLAG_HIDDEN);else lv_obj_add_flag(legend[index],LV_OBJ_FLAG_HIDDEN);
}
// Media task: recording A shows only live; B and A again show live over A.
void chart_recording(unsigned index) {
    if(!bsp_display_lock(1000))return;
    lv_chart_set_all_value(chart,series[0],LV_CHART_POINT_NONE);
    for(unsigned s=0;s<4;++s)show_series(s,s==0 || (s==1 && index>0));
    lv_chart_refresh(chart);bsp_display_unlock();
}
// After each capture, every recorded series so far is overlaid.
void chart_capture(unsigned index,const float* db) {
    if(!bsp_display_lock(1000))return;
    for(size_t i=0;i<spectrum_band_count;++i)lv_chart_set_value_by_id(chart,series[index+1],i,spectrum_chart_value(db[i]));
    for(unsigned s=0;s<4;++s)show_series(s,s>0 && s<=index+1);
    lv_chart_refresh(chart);bsp_display_unlock();
}
void context_clear() {
    lv_obj_add_flag(context_image,LV_OBJ_FLAG_HIDDEN);lv_label_set_text(context_caption,"");
    lv_obj_add_flag(steady_label,LV_OBJ_FLAG_HIDDEN);
}
void chart_clear() {
    for(unsigned s=0;s<4;++s){lv_chart_set_all_value(chart,series[s],LV_CHART_POINT_NONE);show_series(s,false);}
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
    case S::Asking:return "Listening";
    case S::Transcribing:return "Transcribing";
    case S::Confirming:return "Your question";
    case S::RecordingA:return "Recording A";
    case S::Uploading:return "Uploading";
    case S::Waiting:case S::Acknowledging:return "Waiting for guidance";
    case S::Adjust:return "Step 2: move to B";
    case S::ReadyB:return "Step 3: record B";
    case S::RecordingB:return "Recording B over A";
    case S::ReturnA:return "Step 4: back to A";
    case S::RecordingRepeat:return "Recording A again";
    case S::Complete:return "Comparison: A vs B";
    case S::Cancelled:return "Cancelled";
    case S::Offline:return "Offline";
    default:return "Incomplete";
    }
}
void cancel(lv_event_t*) {
    if(!running)return;
    if(final_speech.load()){stop_speech.store(true);return;}
    cancel_requested_us.store(esp_timer_get_time());
    cancelled.store(true);
    lv_label_set_text(label,"Cancelled locally. Waiting for capture/connection cleanup.");
    lv_obj_add_state(action_button,LV_STATE_DISABLED);lv_obj_add_state(ask_button,LV_STATE_DISABLED);
}
// Actions: 1 = action button (Record A, Use, ...), 2 = ask button (Ask, Retry).
void choose(uint8_t value) {
    if(xQueueSend(actions,&value,0)==pdTRUE)
        for(auto* b:{action_button,ask_button})lv_obj_add_state(b,LV_STATE_DISABLED);
}
void action(lv_event_t*) {if(running && !cancelled.load())choose(1);}
void ask(lv_event_t*) {
    if(!running || cancelled.load())return;
    // While listening this button is Stop: the recorder polls the flag between blocks.
    if(listening.load()){stop_question.store(true);lv_obj_add_state(ask_button,LV_STATE_DISABLED);}
    else choose(2);
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
    set_running(true);chart_clear();context_clear();
    lv_label_set_text(heading,"Connecting");
    lv_label_set_text(label,"Connecting to the Mac service...");
}
lv_obj_t* button(lv_obj_t* parent,const char* text,int x,int y,lv_event_cb_t callback,int width=220) {
    auto* b=lv_button_create(parent);lv_obj_set_pos(b,x,y);lv_obj_set_size(b,width,60);
    lv_obj_add_event_cb(b,callback,LV_EVENT_CLICKED,nullptr);
    lv_obj_add_event_cb(b,[](lv_event_t*){pressed_us.store(esp_timer_get_time());},LV_EVENT_PRESSED,nullptr);
    auto* l=lv_label_create(b);lv_label_set_text(l,text);lv_obj_center(l);return b;
}
void show(InvestigationProtocol& p,const char* message,const char* button_text=nullptr,const char* ask_text=nullptr) {
    if(bsp_display_lock(1000)) {
        // A worker completion must never overwrite a locally visible cancel.
        if(cancelled.load())p.cancel();
        lv_label_set_text(heading,heading_text(p.state()));
        using S=InvestigationProtocol::State;const auto state=p.state();
        if(state==S::ReadyA || state==S::Adjust || state==S::ReadyB || state==S::ReturnA)lv_obj_remove_flag(steady_label,LV_OBJ_FLAG_HIDDEN);
        else lv_obj_add_flag(steady_label,LV_OBJ_FLAG_HIDDEN);
        if(state==S::Asking){lv_bar_set_value(level_bar,0,LV_ANIM_OFF);lv_obj_remove_flag(level_bar,LV_OBJ_FLAG_HIDDEN);}
        else lv_obj_add_flag(level_bar,LV_OBJ_FLAG_HIDDEN);
        if(p.state()==InvestigationProtocol::State::Cancelled)lv_label_set_text(label,"Cancelled. This session cannot resume. Start a new investigation.");
        else lv_label_set_text(label,message);
        lv_obj_add_state(action_button,LV_STATE_DISABLED);lv_obj_add_state(ask_button,LV_STATE_DISABLED);
        if((button_text || ask_text) && !p.terminal())xQueueReset(actions);
        if(button_text && !p.terminal()) {
            lv_label_set_text(action_label,button_text);lv_obj_remove_state(action_button,LV_STATE_DISABLED);
        }
        if(ask_text && !p.terminal()) {
            lv_label_set_text(ask_label,ask_text);lv_obj_remove_state(ask_button,LV_STATE_DISABLED);
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
    int64_t last_send_us=0;
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
        // Wi-Fi stalls of 3-4 s (TCP retransmission backoff) failed 2 of 24 uploads with a
        // 2 s budget (20260925-ten-minute-1). Cancel still interrupts the write (ADR-0011).
        constexpr int send_budget_ms=10000;
        int sent=n<=32768?esp_transport_ws_send_raw(ws,static_cast<ws_transport_opcodes_t>(0x81),data,n,send_budget_ms):-1;
        completion_state.cancel_notice=false;
        int error=errno;bool ok=sent==static_cast<int>(n);last_send_us=esp_timer_get_time()-started;
        if(!ok || kind!="capture_chunk") {
            auto* e=diagnostic_event("investigation_transport");
            cJSON_AddStringToObject(e,"message_type",kind.c_str());cJSON_AddNumberToObject(e,"requested_bytes",n);
            cJSON_AddNumberToObject(e,"sent_bytes",sent);cJSON_AddNumberToObject(e,"errno",error);
            cJSON_AddNumberToObject(e,"duration_us",esp_timer_get_time()-started);diagnostic_emit(e);
        }
        cJSON_free(data);return ok;
    }
    // 0 nothing waiting, 1 complete message, 2 part of a message read,
    // -1 protocol/connection error. No network operation runs under the
    // display lock. Ping/pong handled by pinned IDF.
    int poll(int timeout_ms=20) {
        int ready=esp_transport_poll_read(ws,timeout_ms);if(ready<=0)return ready;
        char chunk[1024];int n=esp_transport_read(ws,chunk,sizeof(chunk),1000);
        if(n<0)return -1;
        if(!n)return 0;
        const int result=frames->append(esp_transport_ws_get_read_opcode(ws),esp_transport_ws_get_read_payload_len(ws),
                                        esp_transport_ws_get_fin_flag(ws),chunk,n);
        return result==0?2:result;
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
// The media owner is the IMU's sequential owner; sample it while waiting.
// Returns the chosen action (1 or 2), or 0 when the session ended.
int wait_action(Socket& s,InvestigationProtocol& p,const char* action) {
    uint8_t command;Steadiness steadiness;uint64_t next_sample=0;SteadinessReading reading;
    while(active(p)) {
        const uint64_t now=now_ms();
        if(now>=next_sample) {
            next_sample=now+40;bmi2_sens_data data{};
            if(imu_read_checked(data)==BMI2_OK) {
                const int16_t gyro[3]={data.gyr.x,data.gyr.y,data.gyr.z},accel[3]={data.acc.x,data.acc.y,data.acc.z};
                steadiness.add(now,gyro,accel);
            } else steadiness.fail(now);
            reading=steadiness.read(now);
            portENTER_CRITICAL(&live_lock);steady_reading=reading;steady_fresh=true;portEXIT_CRITICAL(&live_lock);
        }
        int result=s.poll();
        if(result<0){p.disconnect();return false;}
        if(result==1){s.consumed();p.fail();return false;}
        if(xQueueReceive(actions,&command,0)==pdTRUE) {
            reading=steadiness.read(now_ms());
            static const char* names[]={"unknown","steady","moving"};
            auto* e=diagnostic_event("investigation_steadiness");cJSON_AddStringToObject(e,"action",action);
            cJSON_AddNumberToObject(e,"pressed_us",pressed_us.load());
            cJSON_AddStringToObject(e,"state",names[reading.state]);cJSON_AddNumberToObject(e,"peak_dps",reading.peak_dps);
            cJSON_AddNumberToObject(e,"accel_span_g",reading.accel_span_g);cJSON_AddNumberToObject(e,"samples",reading.samples);
            diagnostic_emit(e);
            return active(p)?command:0;
        }
    }
    return 0;
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
// One reusable base64 scratch buffer; at most 4096 raw bytes per message.
// Counts the chunks sent and the slowest chunk write (G-0001.02 upload baseline).
bool send_chunks(Socket& s,InvestigationProtocol& p,const char* type,const char* key,const char* id,const InvestigationCapture& c,
                 unsigned* chunks=nullptr,int64_t* max_us=nullptr) {
    auto* encoded=static_cast<unsigned char*>(malloc(5465));if(!encoded)return false;
    bool ok=true;
    for(size_t offset=0;ok && offset<c.size;offset+=4096) {
        if(!active(p)){ok=false;break;}
        size_t count=std::min(size_t(4096),c.size-offset),written=0;
        ok=mbedtls_base64_encode(encoded,5465,&written,c.bytes+offset,count)==0;
        if(!ok)break;
        encoded[written]=0;
        auto* o=p.envelope(type);cJSON_AddStringToObject(o,key,id);
        cJSON_AddNumberToObject(o,"offset",offset);cJSON_AddStringToObject(o,"data",reinterpret_cast<char*>(encoded));
        ok=s.send(o);
        if(ok && chunks)++*chunks;
        if(max_us)*max_us=std::max(*max_us,s.last_send_us);
    }
    free(encoded);return ok;
}
// ok means the Mac acknowledged the complete capture with its SHA-256.
bool upload(Socket& s,InvestigationProtocol& p,const InvestigationCapture& c,unsigned index) {
    const char* id=p.capture_id(index);auto* o=p.envelope("capture_start");
    cJSON_AddItemToObject(o,"metadata",cJSON_Duplicate(c.metadata,true));
    if(!active(p)){cJSON_Delete(o);return false;}
    const int64_t started=esp_timer_get_time();unsigned chunks=0;int64_t max_chunk_us=0;
    // G-0001.02 Wi-Fi loss: the lowest free internal RAM during this upload.
    const bool monitoring=heap_caps_monitor_local_minimum_free_size_start()==ESP_OK;
    bool ok=s.send(o) && capture_ack(s,p,id,"start") && send_chunks(s,p,"capture_chunk","capture_id",id,c,&chunks,&max_chunk_us);
    const char* sha=cJSON_GetObjectItemCaseSensitive(c.metadata,"sha256")->valuestring;
    if(ok) {
        o=p.envelope("capture_end");cJSON_AddStringToObject(o,"capture_id",id);cJSON_AddStringToObject(o,"sha256",sha);
        if(!active(p)){cJSON_Delete(o);ok=false;}
        else ok=s.send(o) && capture_ack(s,p,id,"complete",sha);
    }
    auto* e=diagnostic_event("investigation_upload");cJSON_AddStringToObject(e,"capture_id",id);
    cJSON_AddBoolToObject(e,"ok",ok);cJSON_AddNumberToObject(e,"bytes",c.size);cJSON_AddNumberToObject(e,"chunks",chunks);
    cJSON_AddNumberToObject(e,"upload_us",esp_timer_get_time()-started);cJSON_AddNumberToObject(e,"max_chunk_us",max_chunk_us);
    if(monitoring) {
        cJSON_AddNumberToObject(e,"min_free_internal",heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL));
        cJSON_AddNumberToObject(e,"min_free_dma",heap_caps_get_minimum_free_size(MALLOC_CAP_DMA));
        heap_caps_monitor_local_minimum_free_size_stop();
    }
    cJSON_AddNumberToObject(e,"largest_internal_block",heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL));
    diagnostic_emit(e);
    return ok;
}

// Spoken question: no per-stage ACKs; the transcript is the completion reply.
bool upload_question(Socket& s,InvestigationProtocol& p,const InvestigationCapture& q) {
    const char* id=p.question_id();auto* o=p.envelope("question_start");
    cJSON_AddItemToObject(o,"metadata",cJSON_Duplicate(q.metadata,true));
    if(!active(p)){cJSON_Delete(o);return false;}
    if(!s.send(o) || !send_chunks(s,p,"question_chunk","question_id",id,q))return false;
    o=p.envelope("question_end");cJSON_AddStringToObject(o,"question_id",id);
    cJSON_AddStringToObject(o,"sha256",cJSON_GetObjectItemCaseSensitive(q.metadata,"sha256")->valuestring);
    if(!active(p)){cJSON_Delete(o);return false;}
    return s.send(o);
}
// Spoken guidance (ADR-0014): ask the Mac to speak an acknowledged reply and
// play it as it streams (24 kHz mono, upsampled to the codec's 48 kHz stereo).
// A tap on an action (when allowed), Cancel, or a failed stream stops playback;
// the stream is still read to its speech_end so the next exchange starts clean,
// except after a session cancel, when the Mac drops it. Returns the tapped action.
// A replay plays muted (G-0001.02 baseline): same codec writes at the same rate.
int speak(Socket& s,InvestigationProtocol& p,const char* request_id,bool actions_allowed,bool audible=true) {
    using S=InvestigationProtocol::State;
    constexpr size_t capacity=60*24000,block=480,prebuffer=12000;
    std::unique_ptr<int16_t,decltype(&free)> audio(static_cast<int16_t*>(
        heap_caps_malloc(capacity*2,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT)),free);
    if(!p.speech_output() || !audio)return 0;
    auto* request=p.envelope("speak");cJSON_AddStringToObject(request,"request_id",request_id);
    if(!s.send(request)){p.disconnect();return 0;}
    SpeechStream stream(p.boot(),p.session(),audio.get(),capacity);stream.begin(request_id);
    auto speaker=diagnostic_speaker();
    esp_codec_dev_sample_info_t format{};format.sample_rate=48000;format.channel=2;format.bits_per_sample=16;
    const bool open=speaker && esp_codec_dev_open(speaker,&format)==ESP_OK &&
        esp_codec_dev_set_out_vol(speaker,100)==ESP_OK && esp_codec_dev_set_out_mute(speaker,!audible)==ESP_OK;
    const int64_t started=esp_timer_get_time();int64_t first_audio=0;
    const uint64_t deadline=now_ms()+90000;
    bool playing=false,stopped=!open,stop_sent=false,failed=false;
    size_t played=0;unsigned underruns=0;int action=0;int16_t previous=0;int64_t stopped_us=0;
    static int16_t output[block*4]; // media task only: 480 frames -> 960 stereo frames
    auto stop_stream=[&]{
        if(stream.ended() || stop_sent)return true;
        stop_sent=true;auto* o=p.envelope("speech_stop");cJSON_AddStringToObject(o,"request_id",request_id);
        return s.send(o);
    };
    if(stopped && !stop_stream()){p.disconnect();failed=true;}
    while(!failed) {
        if(!stopped) {
            uint8_t command;
            if(cancelled.load() || stop_speech.load())stopped=true;
            else if(actions_allowed && xQueueReceive(actions,&command,0)==pdTRUE){action=command;stopped=true;}
            if(stopped) {
                if(open)esp_codec_dev_set_out_mute(speaker,true);
                stopped_us=esp_timer_get_time(); // G-0001.04 C3: playback stops here
                if(cancelled.load() && p.state()!=S::Complete)break; // the session cancel ends the stream
                if(!stop_stream()){p.disconnect();break;}
            }
        }
        if(stream.ended() && (stopped || played>=stream.frames()))break;
        if(now_ms()>=deadline){failed=true;break;}
        if(stream.ended()) {
            // The reply can arrive seconds before it finishes playing. Keep reading so the
            // pinned IDF answers the Mac's keepalive pings (10 s + 10 s, then it closes the
            // socket). No other message is due until the device sends one.
            const int result=s.poll(0);
            if(result<0){p.disconnect();failed=true;break;}
            if(result==1){s.consumed();p.fail();failed=true;break;}
        } else {
            // Up to one whole message per block (speech_receive.h); only the first read may wait.
            int timeout=playing && !stopped?0:20;
            const int result=speech_receive([&]{const int r=s.poll(timeout);timeout=0;return r;},8);
            if(result<0){p.disconnect();failed=true;break;}
            if(result==1) {
                auto* m=InvestigationProtocol::parse(s.buffer);s.consumed();
                const int v=stream.receive(m);cJSON_Delete(m);
                if(v<0){p.fail();failed=true;break;}
                if(!playing)continue;
            }
        }
        if(stopped)continue;
        const size_t buffered=stream.frames()-played;
        if(!playing)playing=buffered>=prebuffer || (stream.ended() && buffered);
        if(!playing)continue;
        if(!buffered){++underruns;playing=false;continue;}
        const size_t n=std::min(block,buffered);
        const int16_t* x=audio.get()+played;
        for(size_t i=0;i<n;++i) {
            const int16_t middle=static_cast<int16_t>((int32_t(previous)+x[i])/2);
            output[i*4]=output[i*4+1]=middle;output[i*4+2]=output[i*4+3]=x[i];previous=x[i];
        }
        if(!first_audio)first_audio=esp_timer_get_time();
        if(esp_codec_dev_write(speaker,output,n*8)!=ESP_OK){stopped=true;if(!stop_stream()){p.disconnect();break;}continue;}
        played+=n;
    }
    if(open && !stopped)vTaskDelay(pdMS_TO_TICKS(100)); // let queued samples drain before muting
    // Close even when the open or its volume/mute setup failed: the device may be marked open.
    if(speaker){if(open)esp_codec_dev_set_out_mute(speaker,true);esp_codec_dev_close(speaker);}
    auto* e=diagnostic_event("investigation_speech");cJSON_AddStringToObject(e,"request_id",request_id);
    cJSON_AddStringToObject(e,"status",stream.status());cJSON_AddNumberToObject(e,"frames",stream.frames());
    cJSON_AddNumberToObject(e,"played_frames",played);cJSON_AddBoolToObject(e,"speaker_open",open);
    cJSON_AddBoolToObject(e,"stopped",stopped);cJSON_AddNumberToObject(e,"action",action);
    cJSON_AddNumberToObject(e,"underruns",underruns);cJSON_AddNumberToObject(e,"stopped_us",stopped_us);
    cJSON_AddNumberToObject(e,"first_audio_ms",first_audio?(first_audio-started)/1000:-1);diagnostic_emit(e);
    return action;
}
// Record, upload and transcribe one question. False when the session ended.
bool ask_question(Socket& s,InvestigationProtocol& p,const char* boot,const char* session) {
    const unsigned number=InvestigationProtocol::max_questions-p.questions_left()+1;
    if(!p.start_question())return false;
    char id[48];snprintf(id,sizeof(id),"%s-q%u",session,number);
    stop_question.store(false);listening.store(true);
    show(p,"Ask your question now, then tap Stop.\nUp to 8 seconds.",nullptr,"Stop");
    InvestigationCapture q;
    const bool recorded=investigation_record_question(boot,session,id,cancelled,stop_question,q,level_tap);
    listening.store(false);
    auto* e=diagnostic_event("investigation_question");cJSON_AddStringToObject(e,"question_id",id);
    cJSON_AddBoolToObject(e,"ok",recorded);
    if(recorded)for(const char* key:{"frames","stopped_by","input_clipped"})
        cJSON_AddItemToObject(e,key,cJSON_Duplicate(cJSON_GetObjectItemCaseSensitive(q.metadata,key),true));
    diagnostic_emit(e);
    if(!recorded || !active(p) || !p.question_recorded(q.metadata,now_ms())){p.fail();return false;}
    show(p,"Transcribing your question on the Mac...");
    const int64_t started=esp_timer_get_time();
    if(!upload_question(s,p,q)){p.fail();return false;}
    const int64_t uploaded=esp_timer_get_time();
    if(!wait_reply(s,p))return false;
    e=diagnostic_event("investigation_transcript");cJSON_AddStringToObject(e,"question_id",id);
    cJSON_AddStringToObject(e,"status",p.transcript_status());
    if(std::isfinite(p.speech_to_noise_db()))cJSON_AddNumberToObject(e,"speech_to_noise_db",p.speech_to_noise_db());
    else cJSON_AddNullToObject(e,"speech_to_noise_db");
    cJSON_AddNumberToObject(e,"upload_us",uploaded-started);
    cJSON_AddNumberToObject(e,"reply_us",esp_timer_get_time()-uploaded);diagnostic_emit(e);
    return active(p);
}
// The host measured this level from the uploaded question (ADR-0012).
std::string level_note(const InvestigationProtocol& p) {
    const double db=p.speech_to_noise_db();char text[96];
    if(!std::isfinite(db))return "Your voice was not measured over the background: check the words.\n";
    snprintf(text,sizeof(text),db<5?"Voice %.0f dB over background: noisy, check the words.\n":
             "Voice %.0f dB over background.\n",db);
    return text;
}
// Before Record A: Ask records a question, a heard transcript needs Use or Retry,
// and Record A goes on with the confirmed (or fixture) question. True when
// Record A was chosen and the session is still active.
bool choose_question(Socket& s,InvestigationProtocol& p,const char* boot,const char* session,
                     const std::string& fixture_question,const std::string& steps) {
    using S=InvestigationProtocol::State;
    std::string notice;
    while(active(p)) {
        if(p.state()==S::Confirming) {
            const bool more=p.questions_left()>0;
            const std::string text="\""+std::string(p.transcript())+"\"\n\n"+level_note(p)+
                (more?"Use this question, or Retry to ask again.":"Use this question, or Discard it.");
            show(p,text.c_str(),"Use",more?"Retry":"Discard");
            const int choice=wait_action(s,p,"confirm_question");
            if(!choice)return false;
            auto* e=diagnostic_event("investigation_question_confirm");
            cJSON_AddStringToObject(e,"question_id",p.question_id());cJSON_AddBoolToObject(e,"accepted",choice==1);
            diagnostic_emit(e);
            if(!s.send(p.confirm_question(choice==1))){p.disconnect();return false;}
            notice=choice==1?"":"Question discarded.\n";
            if(choice==2 && more && !ask_question(s,p,boot,session))return false;
            continue;
        }
        const bool asked=p.question()[0];
        // The guidance box shows about 7 lines: the Ask hint shares the question's line.
        const std::string prompt=notice+(asked?"Your question: "+std::string(p.question()):
            (p.questions_left()?"Tap Ask to ask by voice, or record A for: ":"")+fixture_question)+"\n\n"+steps;
        show(p,prompt.c_str(),"Record A",p.questions_left()?(asked?"Ask again":"Ask"):nullptr);
        const int choice=wait_action(s,p,"record_a");
        if(choice!=2)return choice==1;
        notice.clear();
        if(!ask_question(s,p,boot,session))return false;
        if(p.state()==S::ReadyA)notice=!strcmp(p.transcript_status(),"empty")?
            "Nothing was recognised. Ask again, or record A.\n":"Speech-to-text failed on the Mac. Ask again, or record A.\n";
    }
    return false;
}

// Media task. The image is hidden (under the display lock) while its pixels
// are rewritten, so the synchronous renderer never reads a partial frame.
void take_context_photo() {
    if(!context_pixels)return;
    if(bsp_display_lock(1000)){lv_obj_add_flag(context_image,LV_OBJ_FLAG_HIDDEN);bsp_display_unlock();}
    CameraContextShot shot;
    const bool ok=camera_context_shot(context_pixels,context_width*context_height*2,context_width,context_height,shot);
    if(bsp_display_lock(1000)) {
        if(ok) {
            lv_image_cache_drop(&context_dsc);lv_image_set_src(context_image,&context_dsc);
            lv_obj_remove_flag(context_image,LV_OBJ_FLAG_HIDDEN);lv_obj_invalidate(context_image);
            lv_label_set_text(context_caption,shot.luma<20?"Context (very dark)":"Context");
        } else lv_label_set_text(context_caption,"No context photo (camera error)");
        bsp_display_unlock();
    }
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
    lv_obj_set_width(heading,500);lv_label_set_long_mode(heading,LV_LABEL_LONG_DOT);
    steady_label=text(panel,"Motion: no data",520,6,&lv_font_montserrat_24,0x90a4ae);
    lv_obj_set_width(steady_label,360);lv_label_set_long_mode(steady_label,LV_LABEL_LONG_DOT);
    const char* names[4]={"Live","A","B","A2"};
    const int legend_x[4]={890,965,1015,1065};
    for(unsigned s=0;s<4;++s)legend[s]=text(panel,names[s],legend_x[s],6,&lv_font_montserrat_24,series_colors[s]);

    // 48 log bands, 50 Hz-20 kHz; 0..100 maps floor..ceiling dB.
    constexpr int chart_x=80,chart_y=50,chart_w=1090,chart_h=270;
    chart=lv_chart_create(panel);lv_obj_set_pos(chart,chart_x,chart_y);lv_obj_set_size(chart,chart_w,chart_h);
    lv_chart_set_type(chart,LV_CHART_TYPE_LINE);lv_chart_set_point_count(chart,spectrum_band_count);
    lv_chart_set_range(chart,LV_CHART_AXIS_PRIMARY_Y,0,100);lv_chart_set_div_line_count(chart,5,0);
    lv_obj_set_style_pad_all(chart,0,0);lv_obj_set_style_bg_color(chart,lv_color_hex(0x000000),0);
    lv_obj_set_style_border_color(chart,lv_color_hex(0x37474f),0);
    lv_obj_set_style_line_color(chart,lv_color_hex(0x263238),LV_PART_MAIN);
    lv_obj_set_style_line_width(chart,3,LV_PART_ITEMS);lv_obj_set_style_size(chart,0,0,LV_PART_INDICATOR);
    for(unsigned s=0;s<4;++s)series[s]=lv_chart_add_series(chart,lv_color_hex(series_colors[s]),LV_CHART_AXIS_PRIMARY_Y);
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

    auto* transcript=lv_obj_create(panel);lv_obj_set_pos(transcript,0,355);lv_obj_set_size(transcript,835,190);
    label=lv_label_create(transcript);lv_obj_set_width(label,790);
    lv_obj_set_style_text_font(label,&lv_font_montserrat_22,0);
    lv_label_set_long_mode(label,LV_LABEL_LONG_WRAP);
    lv_label_set_text(label,"Steady sound A/B test. Record at A, move, record at B, then compare.\nKeep the source level and device orientation fixed. Tap Start.");
    context_pixels=static_cast<uint16_t*>(heap_caps_calloc(1,context_width*context_height*2,MALLOC_CAP_SPIRAM));
    context_dsc.header.magic=LV_IMAGE_HEADER_MAGIC;context_dsc.header.cf=LV_COLOR_FORMAT_RGB565;
    context_dsc.header.w=context_width;context_dsc.header.h=context_height;context_dsc.header.stride=context_width*2;
    context_dsc.data_size=context_width*context_height*2;context_dsc.data=reinterpret_cast<const uint8_t*>(context_pixels);
    context_image=lv_image_create(panel);lv_obj_set_pos(context_image,850,355);lv_obj_set_size(context_image,context_width,context_height);
    context_caption=text(panel,"",850,355+context_height+2,&lv_font_montserrat_16,0x90a4ae);
    start_button=button(panel,"Start",0,560,start,180);
    ask_button=button(panel,"Ask",192,560,ask,180);ask_label=lv_obj_get_child(ask_button,0);
    lv_obj_add_state(ask_button,LV_STATE_DISABLED);
    action_button=button(panel,"Record A",384,560,action,180);action_label=lv_obj_get_child(action_button,0);
    lv_obj_add_state(action_button,LV_STATE_DISABLED);
    cancel_button=button(panel,"Cancel",576,560,cancel,180);lv_obj_add_state(cancel_button,LV_STATE_DISABLED);
    setup_button=button(panel,"Setup",768,560,open_setup,180);
    back_button=button(panel,"Back",960,560,back,180);
    // Question input level, shown only while listening, where the steadiness label sits.
    level_bar=lv_bar_create(panel);lv_obj_set_pos(level_bar,520,8);lv_obj_set_size(level_bar,360,28);
    lv_bar_set_range(level_bar,0,100);
    lv_obj_set_style_bg_color(level_bar,lv_color_hex(0x263238),LV_PART_MAIN);
    lv_obj_set_style_bg_color(level_bar,lv_color_hex(0x66bb6a),LV_PART_INDICATOR);
    lv_timer_create(draw_live,60,nullptr);
    lv_timer_create([](lv_timer_t*){ui_pulse.tick(esp_timer_get_time());},20,nullptr);

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
    diagnostic_check("investigation_layout",layout_ok(panel,{heading,steady_label,legend[0],legend[1],legend[2],legend[3],chart,transcript,context_image,start_button,ask_button,action_button,cancel_button,setup_button,back_button})?"pass":"fail",
                     "Resolved A/B heading, spectrum, guidance and buttons stay inside the panel without overlap.");
    diagnostic_check("investigation_level_layout",layout_ok(panel,{heading,level_bar,legend[0],chart})?"pass":"fail",
                     "The question level meter stays inside the panel, clear of the heading, legend and spectrum.");
    lv_obj_add_flag(level_bar,LV_OBJ_FLAG_HIDDEN);
    for(auto* p:{panel,setup_panel,keyboard})lv_obj_add_flag(p,LV_OBJ_FLAG_HIDDEN);
    context_clear();
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
    if(bsp_display_lock(1000)){ui_pulse.reset();bsp_display_unlock();}
    stop_speech.store(false); // a Cancel during the last session's final speech must not silence this one
    Socket socket;
    std::unique_ptr<cJSON,decltype(&cJSON_Delete)> fixture(
        cJSON_ParseWithLength(reinterpret_cast<const char*>(fixture_start),fixture_end-fixture_start),cJSON_Delete);
    auto fixture_text=[&](const char* key) {
        auto* value=cJSON_GetObjectItemCaseSensitive(fixture.get(),key);
        return cJSON_IsString(value)?value->valuestring:"";
    };
    // The fixture holds capture settings and a default question. What A and B
    // are comes from the person's question and the guidance, not the fixture.
    const std::string question=fixture_text("question");
    if(question.empty())p->fail();
    if(!active(*p) || !endpoint.parse(endpoint_text) || !socket.connect(endpoint))p->disconnect();
    else if(active(*p)) {
        auto* hello=p->envelope("hello");
        if(replay)cJSON_AddBoolToObject(hello,"replay",true);
        cJSON_AddItemToObject(hello,"fixture",cJSON_Duplicate(fixture.get(),true));
        if(!socket.send(hello))p->disconnect();else wait_reply(socket,*p);
    }
    if(!replay && active(*p)) {
        show(*p,"Point the camera at what you are investigating.\nTaking a context photo...");
        if(context_photo_enabled.load())take_context_photo();
    }
    // A, B, then back to A for a repeat (SD replay resends a saved pair only).
    static const char* steps_text[3]={
        "Record A where you are now. Hold still: three seconds, speaker silent.",
        "Record B where the guidance sent you, holding the device the same way. Hold still: three seconds.",
        "Go back to A and hold the device the same way, then record A again.\nThis shows how much the reading changes when nothing else does."};
    static const char* record_text[3]={"Record A","Record B","Record A again"};
    static const char* action_name[3]={"record_a","record_b","record_repeat"};
    for(unsigned index=0;index<(replay?2u:3u) && active(*p);++index) {
        const std::string steps=steps_text[index];
        if(index==0 && !replay && p->speech_available()) {
            if(!choose_question(socket,*p,boot,session,question,steps))break;
        } else {
            const std::string prompt=(p->question()[0]?"Your question: "+std::string(p->question()):question)+"\n\n"+steps;
            show(*p,replay?"SD REPLAY: loading original recordings. No new sensor acquisition.":prompt.c_str(),replay?nullptr:record_text[index]);
            if(!replay && !wait_action(socket,*p,action_name[index]))break;
        }
        if(!p->start_capture())break;
        static const char* settling[3]={"Settling 0.5s, then recording A / 3s\nHold still; speaker silent.",
            "Settling 0.5s, then recording B / 3s\nHold still; speaker silent.",
            "Settling 0.5s, then recording A again / 3s\nHold still; speaker silent."};
        if(!replay)show(*p,settling[index]);
        {
            InvestigationCapture capture;char id[48];snprintf(id,sizeof(id),"%s-%c",session,"abr"[index]);
            if(!replay)chart_recording(index);
            const bool loaded=replay?test_storage_load_capture(id,capture):investigation_capture(boot,session,id,cancelled,capture,live_tap);
            if(!loaded || !active(*p) ||
               !p->captured(capture.metadata,capture.measurement,now_ms())){p->fail();break;}
            float db[spectrum_band_count];
            if(capture_bands(capture,db))chart_capture(index,db);
            show(*p,replay?"SD REPLAY: uploading original verified recording...":"Uploading the verified recording...");
            // The SD copy (about 3.4 s) is written after the Mac holds the verified
            // bytes, during a wait the person has anyway: the Mac's reply, or the
            // walk back to A. A failed upload is still saved so it isn't lost.
            auto save=[&]{if(!replay && sd_archive_enabled.load())test_storage_archive(capture.bytes,capture.size,capture.metadata);};
            if(!upload(socket,*p,capture,index)){save();p->fail();break;}
            if(!active(*p))break;
            if(index==1 && !replay) {
                if(!p->await_repeat())break;
                show(*p,(std::string(steps_text[2])+"\n(Saving B to SD...)").c_str());
                save();continue;
            }
            if(!socket.send(p->turn(now_ms()))){p->disconnect();break;}
            show(*p,"Waiting for evidence-linked guidance...\nCancel is available.");
            save();
        } // Raw PCM is freed after its hash ACK and SD copy.
        if(!wait_reply(socket,*p))break;
        if(!active(*p))break;
        if(!socket.send(p->ack())){p->disconnect();break;}
        if(!wait_reply(socket,*p))break;
        if(index==0) {
            show(*p,p->text(),replay?nullptr:"Confirm position B");
            // The guidance is spoken while Confirm is live; a tap stops the speech and goes on.
            // A replay speaks only when the service offers speech (G-0001.02 playback baseline).
            const int chosen=speak(socket,*p,"r1",!replay,!replay);
            if(!active(*p))break;
            if((!replay && !chosen && !wait_action(socket,*p,"confirm_b")) || !p->adjust(replay?"SD replay of original recorded A/B adjustment; no new movement":
                                                                            "Moved to B as the guidance described; device held the same way"))break;
        }
    }
    if(cancelled.load()) {
        p->cancel();
        auto* e=diagnostic_event("investigation_cancel");
        cJSON_AddStringToObject(e,"session_id",session);
        cJSON_AddNumberToObject(e,"requested_device_us",cancel_requested_us.load());
        cJSON_AddNumberToObject(e,"owner_stopped_device_us",esp_timer_get_time());
        diagnostic_emit(e);
        if(socket.ws && p->state()==InvestigationProtocol::State::Cancelled)socket.send(p->envelope("cancel"));
    }
    if(!p->terminal())p->fail();
    const char* final_text=p->state()==InvestigationProtocol::State::Complete?p->text():
        p->state()==InvestigationProtocol::State::Offline?"Offline. Check Wi-Fi and the Mac service. Start a new investigation; this session cannot resume.":
        "Incomplete. No valid comparison. Check the retained run evidence, then start a new investigation.";
    const std::string displayed=replay?std::string("SD REPLAY (no new acquisition)\n")+final_text:final_text;
    show(*p,displayed.c_str());
    if(p->state()==InvestigationProtocol::State::Complete) {
        stop_speech.store(false);final_speech.store(true);
        speak(socket,*p,"r2",false,!replay);
        final_speech.store(false);
    }
    if(bsp_display_lock(1000)) {
        set_running(false);show_series(0,false);
        bsp_display_unlock();
    }
    // After running is cleared, so a host waiting on this can start the next replay.
    auto* e=diagnostic_event("investigation_end");cJSON_AddStringToObject(e,"session_id",session);
    cJSON_AddStringToObject(e,"state",p->state_name());cJSON_AddBoolToObject(e,"replay",replay!=nullptr);
    // G-0001.02: LVGL probe intervals over the session, and memory after it.
    if(bsp_display_lock(1000)) {
        cJSON_AddNumberToObject(e,"ui_intervals",ui_pulse.count());
        cJSON_AddNumberToObject(e,"ui_p50_ms",ui_pulse.percentile_ms(0.50));
        cJSON_AddNumberToObject(e,"ui_p95_ms",ui_pulse.percentile_ms(0.95));
        cJSON_AddNumberToObject(e,"ui_max_us",ui_pulse.max_us());
        cJSON_AddNumberToObject(e,"ui_over_50_ms",ui_pulse.over_ms(50));
        cJSON_AddNumberToObject(e,"ui_over_200_ms",ui_pulse.over_ms(200));
        auto* longs=cJSON_AddArrayToObject(e,"ui_long");
        for(unsigned i=0;i<ui_pulse.long_count();++i) {
            auto* item=cJSON_CreateArray();const auto l=ui_pulse.long_at(i);
            cJSON_AddItemToArray(item,cJSON_CreateNumber(l.end_us));cJSON_AddItemToArray(item,cJSON_CreateNumber(l.duration_us));
            cJSON_AddItemToArray(longs,item);
        }
        bsp_display_unlock();
    }
    cJSON_AddNumberToObject(e,"free_internal",heap_caps_get_free_size(MALLOC_CAP_INTERNAL));
    cJSON_AddNumberToObject(e,"free_psram",heap_caps_get_free_size(MALLOC_CAP_SPIRAM));
    cJSON_AddNumberToObject(e,"largest_psram_block",heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM));
    cJSON_AddNumberToObject(e,"min_free_internal",heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL));
    diagnostic_emit(e);
}

void investigation_run(const char* boot) {run_investigation(boot);}
bool investigation_set(const char* name,bool value) {
    if(!strcmp(name,"sd_archive"))sd_archive_enabled.store(value);
    else if(!strcmp(name,"context_photo"))context_photo_enabled.store(value);
    else return false;
    return true;
}
// USB console input for automated sessions: the same LVGL click handler a
// finger reaches, and only on a visible, enabled button.
bool investigation_tap(const char* name) {
    if(!bsp_display_lock(1000))return false;
    lv_obj_t* b=!strcmp(name,"start")?start_button:!strcmp(name,"action")?action_button:
                !strcmp(name,"ask")?ask_button:!strcmp(name,"cancel")?cancel_button:nullptr;
    const bool ok=b && lv_obj_is_visible(b) && !lv_obj_has_state(b,LV_STATE_DISABLED);
    if(ok)lv_obj_send_event(b,LV_EVENT_CLICKED,nullptr);
    bsp_display_unlock();return ok;
}
bool investigation_request_replay(const char* session) {
    if(!investigation_replay_session(session) || !media_queue || !bsp_display_lock(1000))return false;
    InvestigationEndpoint endpoint;bool ok=!running && endpoint.parse(lv_textarea_get_text(endpoint_field));
    if(ok) {
        strcpy(endpoint_text,lv_textarea_get_text(endpoint_field));strcpy(replay_session_text,session);
        cancel_requested_us.store(0);cancelled.store(false);xQueueReset(actions);
        uint8_t command=5;ok=xQueueSend(media_queue,&command,0)==pdTRUE;
        if(ok) {
            set_running(true);chart_clear();context_clear();lv_obj_add_flag(setup_panel,LV_OBJ_FLAG_HIDDEN);
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
