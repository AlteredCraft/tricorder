#include "investigation.h"
#include "investigation_protocol.h"
#include "investigation_wire.h"
#include "investigation_capture.h"
#include "test_storage.h"
#include "diagnostic_events.h"
#include "bsp/m5stack_tab5.h"
#include "esp_transport.h"
#include "esp_transport_tcp.h"
#include "esp_transport_ws.h"
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

extern const uint8_t fixture_start[] asm("_binary_guided_ab_fixture_json_start");
extern const uint8_t fixture_end[] asm("_binary_guided_ab_fixture_json_end");
namespace {
lv_obj_t *launch,*panel,*label,*endpoint_field,*keyboard,*start_button,*action_button,*action_label,*back_button,*cancel_button;
QueueHandle_t media_queue,actions;
std::atomic<bool> cancelled{false};
std::atomic<int64_t> cancel_requested_us{0};
bool running=false; // Access only under the display lock.
char endpoint_text[241]{};
char replay_session_text[40]{};
uint64_t now_ms(){return esp_timer_get_time()/1000;}

void open(lv_event_t*) {lv_obj_remove_flag(panel,LV_OBJ_FLAG_HIDDEN);lv_obj_move_foreground(panel);}
void back(lv_event_t*) {if(!running)lv_obj_add_flag(panel,LV_OBJ_FLAG_HIDDEN);}
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
void start(lv_event_t*) {
    if(running)return;
    InvestigationEndpoint endpoint;
    const char* text=lv_textarea_get_text(endpoint_field);
    if(!endpoint.parse(text)){lv_label_set_text(label,"Enter ws://Mac-LAN-IP:8765/ then start. Join Wi-Fi first.");return;}
    strcpy(endpoint_text,text);cancel_requested_us.store(0);cancelled.store(false);xQueueReset(actions);
    uint8_t command=4;
    if(xQueueSend(media_queue,&command,0)!=pdTRUE){lv_label_set_text(label,"Media owner busy. Try again.");return;}
    running=true;lv_obj_add_flag(keyboard,LV_OBJ_FLAG_HIDDEN);
    for(auto* b:{start_button,back_button,endpoint_field})lv_obj_add_state(b,LV_STATE_DISABLED);
    lv_obj_remove_state(cancel_button,LV_STATE_DISABLED);
    lv_label_set_text(label,"Connecting to the mock service...");
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

class Socket {
public:
    esp_transport_handle_t tcp=nullptr,ws=nullptr;
    char* buffer=nullptr;
    std::unique_ptr<InvestigationFrames> frames;
    Socket() {
        buffer=static_cast<char*>(heap_caps_malloc(32769,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
        if(buffer)frames.reset(new InvestigationFrames(buffer));
        tcp=esp_transport_tcp_init();if(tcp)ws=esp_transport_ws_init(tcp);
    }
    ~Socket() {if(ws){esp_transport_close(ws);esp_transport_destroy(ws);}if(tcp)esp_transport_destroy(tcp);free(buffer);}
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
        int sent=n<=32768?esp_transport_ws_send_raw(ws,static_cast<ws_transport_opcodes_t>(0x81),data,n,2000):-1;
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
}

void investigation_ui_init(lv_obj_t* screen,QueueHandle_t media_commands) {
    media_queue=media_commands;actions=xQueueCreate(1,sizeof(uint8_t));configASSERT(actions);
    launch=button(screen,"Guided A/B",30,220,open);lv_obj_add_state(launch,LV_STATE_DISABLED);
    panel=lv_obj_create(screen);lv_obj_set_size(panel,1220,680);lv_obj_center(panel);
    lv_obj_add_flag(panel,LV_OBJ_FLAG_HIDDEN);
    endpoint_field=lv_textarea_create(panel);lv_obj_set_pos(endpoint_field,15,10);lv_obj_set_size(endpoint_field,900,55);
    lv_textarea_set_one_line(endpoint_field,true);lv_textarea_set_max_length(endpoint_field,240);
    lv_textarea_set_placeholder_text(endpoint_field,"ws://Mac-LAN-IP:8765/");
    lv_textarea_set_text(endpoint_field,CONFIG_TRICORDER_INVESTIGATION_ENDPOINT);
    start_button=button(panel,"Start mock",935,10,start);
    auto* transcript=lv_obj_create(panel);lv_obj_set_pos(transcript,0,85);lv_obj_set_size(transcript,1190,455);
    label=lv_label_create(transcript);lv_obj_set_width(label,1140);
    lv_label_set_long_mode(label,LV_LABEL_LONG_WRAP);
    lv_label_set_text(label,"Steady speaker A/B test. Join Wi-Fi before opening this screen.\nEnter the Mac service address. Keep source level and orientation fixed.");
    keyboard=lv_keyboard_create(panel);lv_obj_set_size(keyboard,1160,270);lv_obj_align(keyboard,LV_ALIGN_TOP_LEFT,15,270);
    lv_keyboard_set_textarea(keyboard,endpoint_field);
    lv_obj_add_event_cb(endpoint_field,edit_endpoint,LV_EVENT_FOCUSED,nullptr);
    action_button=button(panel,"Record A",15,560,action);action_label=lv_obj_get_child(action_button,0);
    lv_obj_add_state(action_button,LV_STATE_DISABLED);
    cancel_button=button(panel,"Cancel",260,560,cancel);lv_obj_add_state(cancel_button,LV_STATE_DISABLED);
    back_button=button(panel,"Back",935,560,back);
    // Device-side geometry check uses LVGL's resolved positions, including
    // constructor alignment, rather than assuming set_pos is absolute.
    lv_obj_remove_flag(panel,LV_OBJ_FLAG_HIDDEN);
    lv_obj_update_layout(panel);
    lv_area_t panel_area{},keyboard_area{};
    lv_obj_get_coords(panel,&panel_area);lv_obj_get_coords(keyboard,&keyboard_area);
    const bool inside=keyboard_area.x1>=panel_area.x1 && keyboard_area.y1>=panel_area.y1 &&
        keyboard_area.x2<=panel_area.x2 && keyboard_area.y2<=panel_area.y2;
    diagnostic_check("investigation_keyboard_layout",inside?"pass":"fail",
                     "Resolved keyboard rectangle must stay inside the A/B panel.");
    lv_obj_add_flag(panel,LV_OBJ_FLAG_HIDDEN);
}
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
            const bool loaded=replay?test_storage_load_capture(id,capture):investigation_capture(boot,session,id,cancelled,capture);
            if(!loaded || !active(*p) ||
               !p->captured(capture.metadata,capture.measurement,now_ms())){p->fail();break;}
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
        running=false;
        for(auto* b:{start_button,back_button,endpoint_field})lv_obj_remove_state(b,LV_STATE_DISABLED);
        lv_obj_add_state(cancel_button,LV_STATE_DISABLED);
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
            running=true;lv_obj_remove_flag(panel,LV_OBJ_FLAG_HIDDEN);lv_obj_move_foreground(panel);
            lv_obj_add_flag(keyboard,LV_OBJ_FLAG_HIDDEN);
            for(auto* b:{start_button,back_button,endpoint_field})lv_obj_add_state(b,LV_STATE_DISABLED);
            lv_obj_remove_state(cancel_button,LV_STATE_DISABLED);
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
        running=false;lv_label_set_text(label,"SD REPLAY failed: saved recording missing or invalid.");
        for(auto* b:{start_button,back_button,endpoint_field})lv_obj_remove_state(b,LV_STATE_DISABLED);
        lv_obj_add_state(cancel_button,LV_STATE_DISABLED);bsp_display_unlock();
    }
}

void investigation_set_endpoint(const char* endpoint) {
    if(bsp_display_lock(1000)) {
        if(!running)lv_textarea_set_text(endpoint_field,endpoint);
        bsp_display_unlock();
    }
}
