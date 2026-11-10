#include "service_client.h"
#include "service_protocol.h"
#include "service_wire.h"
#include "transport_write.h"
#include "speech_stream.h"
#include "speech_receive.h"
#include "audio_devices.h"
#include "diagnostic_events.h"
#include "setup.h"
#include "esp_transport.h"
#include "esp_transport_tcp.h"
#include "esp_transport_ws.h"
#include "esp_transport_internal.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "mbedtls/base64.h"
#include <algorithm>
#include <atomic>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <string>

// The device's side of the Mac service (planning/service.md): one WebSocket session per
// Explain, on the media task. Sends the analysis (and a photo or voice note), shows the
// reply and plays it as the Mac speaks it.
namespace {
std::atomic<bool> stop_speech{false};
char endpoint_text[241]{};
uint64_t now_ms(){return esp_timer_get_time()/1000;}

// The pinned TCP writer may return a positive short count. Complete that byte
// range below WS framing, under its original budget; a fresh WS send would
// corrupt the unfinished frame. All handles remain owned by the media worker.
struct TcpCompletion {
    esp_transport_handle_t tcp=nullptr;
    bool failed=false;
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
                auto* e=diagnostic_event("service_tcp_short_write");
                cJSON_AddNumberToObject(e,"requested_bytes",count);
                cJSON_AddNumberToObject(e,"sent_bytes",sent);diagnostic_emit(e);
            }
            return sent;
        },now_ms,[]{return false;});
    if(result!=size)state.failed=true;
    return result;
}

class Socket {
public:
    esp_transport_handle_t tcp=nullptr,complete_tcp=nullptr,ws=nullptr;
    TcpCompletion completion_state;
    char* buffer=nullptr;
    std::unique_ptr<ServiceFrames> frames;
    int64_t last_send_us=0;
    Socket() {
        buffer=static_cast<char*>(heap_caps_malloc(32769,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
        if(buffer)frames.reset(new ServiceFrames(buffer));
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
    bool connect(const ServiceEndpoint& e) {
        if(!ws || !buffer)return false;
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
        // Wi-Fi stalls of 3-4 s (TCP retransmission backoff) failed 2 of 24 uploads with a
        // 2 s budget (20260925-ten-minute-1). Nothing more is sent after a failed or
        // partial write (ADR-0011).
        constexpr int send_budget_ms=10000;
        int sent=n<=32768?esp_transport_ws_send_raw(ws,static_cast<ws_transport_opcodes_t>(0x81),data,n,send_budget_ms):-1;
        int error=errno;bool ok=sent==static_cast<int>(n);last_send_us=esp_timer_get_time()-started;
        if(!ok || (kind!="photo_chunk" && kind!="question_chunk")) {
            auto* e=diagnostic_event("service_transport");
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

bool active(ServiceProtocol& p) {p.tick(now_ms());return !p.terminal();}
bool wait_reply(Socket& s,ServiceProtocol& p) {
    while(active(p)) {
        int result=s.poll();
        if(result<0){p.disconnect();return false;}
        if(result==1) {
            // Recheck the deadline after a blocking read, before consuming a reply.
            if(!active(p))return false;
            bool ok=p.receive(s.buffer,now_ms());s.consumed();
            if(!ok)p.fail();
            return ok;
        }
    }
    return false;
}
// One reusable base64 scratch buffer; at most 4096 raw bytes per message.
// Counts the chunks sent and the slowest chunk write.
bool send_chunks(Socket& s,ServiceProtocol& p,const char* type,const char* key,const char* id,
                 const unsigned char* bytes,size_t size,unsigned* chunks=nullptr,int64_t* max_us=nullptr) {
    auto* encoded=static_cast<unsigned char*>(malloc(5465));if(!encoded)return false;
    bool ok=true;
    for(size_t offset=0;ok && offset<size;offset+=4096) {
        if(!active(p)){ok=false;break;}
        size_t count=std::min(size_t(4096),size-offset),written=0;
        ok=mbedtls_base64_encode(encoded,5465,&written,bytes+offset,count)==0;
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
// Voice note: no per-stage ACKs; the transcript is the completion reply.
bool upload_question(Socket& s,ServiceProtocol& p,const VoiceNote& q) {
    const char* id=p.question_id();auto* o=p.envelope("question_start");
    cJSON_AddItemToObject(o,"metadata",cJSON_Duplicate(q.metadata,true));
    if(!active(p)){cJSON_Delete(o);return false;}
    if(!s.send(o) || !send_chunks(s,p,"question_chunk","question_id",id,q.bytes,q.size))return false;
    o=p.envelope("question_end");cJSON_AddStringToObject(o,"question_id",id);
    cJSON_AddStringToObject(o,"sha256",cJSON_GetObjectItemCaseSensitive(q.metadata,"sha256")->valuestring);
    if(!active(p)){cJSON_Delete(o);return false;}
    return s.send(o);
}
// Spoken reply (ADR-0014): ask the Mac to speak the reply it just sent and play it as
// it streams (24 kHz mono, upsampled to the codec's 48 kHz stereo). service_stop_speech
// or a failed stream stops playback; the stream is still read to its speech_end so the
// socket closes clean.
void speak(Socket& s,ServiceProtocol& p,const char* request_id) {
    constexpr size_t capacity=60*24000,block=480,prebuffer=12000;
    std::unique_ptr<int16_t,decltype(&free)> audio(static_cast<int16_t*>(
        heap_caps_malloc(capacity*2,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT)),free);
    if(!p.speech_output() || !audio)return;
    auto* request=p.envelope("speak");cJSON_AddStringToObject(request,"request_id",request_id);
    if(!s.send(request)){p.disconnect();return;}
    SpeechStream stream(p.boot(),p.session(),audio.get(),capacity);stream.begin(request_id);
    auto speaker=diagnostic_speaker();
    bool headphones=route_speaker();
    esp_codec_dev_sample_info_t format{};format.sample_rate=48000;format.channel=2;format.bits_per_sample=16;
    const bool open=speaker && esp_codec_dev_open(speaker,&format)==ESP_OK &&
        esp_codec_dev_set_out_vol(speaker,100)==ESP_OK && esp_codec_dev_set_out_mute(speaker,false)==ESP_OK;
    const int64_t started=esp_timer_get_time();int64_t first_audio=0;
    const uint64_t deadline=now_ms()+90000;
    bool playing=false,stopped=!open,stop_sent=false,failed=false;
    size_t played=0;unsigned underruns=0,blocks=0;int16_t previous=0;int64_t stopped_us=0;
    static int16_t output[block*4]; // media task only: 480 frames -> 960 stereo frames
    auto stop_stream=[&]{
        if(stream.ended() || stop_sent)return true;
        stop_sent=true;auto* o=p.envelope("speech_stop");cJSON_AddStringToObject(o,"request_id",request_id);
        return s.send(o);
    };
    if(stopped && !stop_stream()){p.disconnect();failed=true;}
    while(!failed) {
        if(!stopped && stop_speech.load()) {
            stopped=true;
            if(open)esp_codec_dev_set_out_mute(speaker,true);
            stopped_us=esp_timer_get_time(); // playback stops here
            if(!stop_stream()){p.disconnect();break;}
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
                auto* m=ServiceProtocol::parse(s.buffer);s.consumed();
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
        if(++blocks%12==0)headphones=route_speaker(); // ~240 ms: plugging in mid-reply silences the speaker
    }
    if(open && !stopped)vTaskDelay(pdMS_TO_TICKS(100)); // let queued samples drain before muting
    // Close even when the open or its volume/mute setup failed: the device may be marked open.
    if(speaker){if(open)esp_codec_dev_set_out_mute(speaker,true);esp_codec_dev_close(speaker);}
    auto* e=diagnostic_event("service_speech");cJSON_AddStringToObject(e,"request_id",request_id);
    cJSON_AddStringToObject(e,"status",stream.status());cJSON_AddNumberToObject(e,"frames",stream.frames());
    cJSON_AddNumberToObject(e,"played_frames",played);cJSON_AddBoolToObject(e,"speaker_open",open);cJSON_AddBoolToObject(e,"headphones",headphones);
    cJSON_AddBoolToObject(e,"stopped",stopped);
    cJSON_AddNumberToObject(e,"underruns",underruns);cJSON_AddNumberToObject(e,"stopped_us",stopped_us);
    cJSON_AddNumberToObject(e,"first_audio_ms",first_audio?(first_audio-started)/1000:-1);diagnostic_emit(e);
}
}

void service_stop_speech() {stop_speech.store(true);}

// Media owner: the Mac's reading of an instrument's analysis (service_client.h).
bool service_explain_analysis(const char* boot,const char* session,const VoiceNote* note,
                              cJSON* analysis,const AnalysisExplainHooks& hooks,AnalysisExplainResult& out,
                              const unsigned char* photo,size_t photo_bytes) {
    auto progress=hooks.progress;
    std::unique_ptr<cJSON,decltype(&cJSON_Delete)> summary(analysis,cJSON_Delete);
    auto* kind_item=cJSON_GetObjectItemCaseSensitive(analysis,"kind");
    const std::string kind=cJSON_IsString(kind_item)?kind_item->valuestring:"sound";
    ServiceEndpoint endpoint;
    auto p=std::make_unique<ServiceProtocol>(boot,session);p->ask(now_ms());
    stop_speech.store(false);
    Socket socket;
    const int64_t started=esp_timer_get_time();int64_t connected=0,transcribed=0,replied=0;
    const char* transcript_status="none";
    auto finish=[&](const char* error) {
        if(error)out.error=error;
        auto* e=diagnostic_event("analysis_explain");cJSON_AddStringToObject(e,"session_id",session);
        cJSON_AddStringToObject(e,"kind",kind.c_str());
        cJSON_AddBoolToObject(e,"ok",!error);if(error)cJSON_AddStringToObject(e,"error",error);
        cJSON_AddBoolToObject(e,"note",note!=nullptr);cJSON_AddStringToObject(e,"transcript_status",transcript_status);
        cJSON_AddStringToObject(e,"protocol_state",p->state_name());
        auto ms=[&](int64_t at){return at?(at-started)/1000.0:-1.0;};
        cJSON_AddNumberToObject(e,"connected_ms",ms(connected));cJSON_AddNumberToObject(e,"transcribed_ms",ms(transcribed));
        cJSON_AddNumberToObject(e,"replied_ms",ms(replied));cJSON_AddBoolToObject(e,"spoke",out.spoke);
        cJSON_AddBoolToObject(e,"dialog",hooks.show_transcript!=nullptr);cJSON_AddNumberToObject(e,"choice",out.choice);
        cJSON_AddNumberToObject(e,"text_bytes",out.text.size());diagnostic_emit(e);
        return !error;
    };
    progress("Connecting to the Mac...",nullptr,nullptr);
    setup_endpoint(endpoint_text,sizeof(endpoint_text));
    if(!endpoint.parse(endpoint_text) || !socket.connect(endpoint))
        return finish("Could not reach the Mac service. Check Wi-Fi and the service address in Setup.");
    if(!socket.send(p->envelope("hello")) || !wait_reply(socket,*p) || p->state()!=ServiceProtocol::State::Ready)
        return finish("The Mac service did not answer.");
    connected=esp_timer_get_time();
    if(note && p->speech_available()) {
        progress("Transcribing your voice note...",nullptr,nullptr);
        if(!p->start_question() || !p->question_recorded(note->metadata,now_ms()) || !upload_question(socket,*p,*note) ||
           !wait_reply(socket,*p))return finish("The voice note could not be transcribed.");
        transcript_status=p->transcript_status();transcribed=esp_timer_get_time();
        const bool heard=p->state()==ServiceProtocol::State::Confirming;
        if(hooks.show_transcript) {
            // Waiting for the person: keep reading so the IDF answers the Mac's pings.
            hooks.show_transcript(transcript_status,heard?p->transcript():"");
            const uint64_t until=now_ms()+300000;int choice;
            while((choice=hooks.poll_choice())<0) {
                if(now_ms()>=until){choice=0;break;}
                const int result=socket.poll(20);
                if(result<0)return finish("The connection dropped.");
                if(result==1){socket.consumed();return finish("The Mac sent an unexpected reply.");}
            }
            out.choice=choice;
            if(choice!=1)return finish(nullptr);
        }
        if(heard) {
            out.transcript=p->transcript();
            if(!socket.send(p->confirm_question(true)))return finish("The connection dropped.");
        }
    }
    char request_id[64];snprintf(request_id,sizeof(request_id),"%s-explain",session);
    if(photo && photo_bytes) {
        progress("Sending the photo...",nullptr,nullptr);
        const int64_t sending=esp_timer_get_time();unsigned chunks=0;int64_t max_chunk_us=0;
        const bool sent=send_chunks(socket,*p,"photo_chunk","request_id",request_id,photo,photo_bytes,&chunks,&max_chunk_us);
        auto* e=diagnostic_event("analysis_photo_upload");cJSON_AddStringToObject(e,"session_id",session);
        cJSON_AddBoolToObject(e,"ok",sent);cJSON_AddNumberToObject(e,"bytes",photo_bytes);cJSON_AddNumberToObject(e,"chunks",chunks);
        cJSON_AddNumberToObject(e,"upload_us",esp_timer_get_time()-sending);cJSON_AddNumberToObject(e,"max_chunk_us",max_chunk_us);
        diagnostic_emit(e);
        if(!sent)return finish("The photo could not be sent.");
    }
    progress("Asking the agent...",out.transcript.c_str(),nullptr);
    auto* ask=p->envelope("analysis_explain");cJSON_AddStringToObject(ask,"request_id",request_id);
    cJSON_AddItemToObject(ask,"analysis",summary.release());
    if(!socket.send(ask))return finish("The connection dropped.");
    const uint64_t deadline=now_ms()+45000;
    while(out.text.empty()) {
        if(now_ms()>=deadline)return finish("The agent took too long to answer.");
        const int result=socket.poll();
        if(result<0)return finish("The connection dropped.");
        if(result!=1)continue;
        std::unique_ptr<cJSON,decltype(&cJSON_Delete)> m(ServiceProtocol::parse(socket.buffer),cJSON_Delete);socket.consumed();
        auto* type=cJSON_GetObjectItemCaseSensitive(m.get(),"type");
        auto* id=cJSON_GetObjectItemCaseSensitive(m.get(),"request_id");
        auto* text=cJSON_GetObjectItemCaseSensitive(m.get(),"text");
        if(!m || !p->same_session(m.get()) || !cJSON_IsString(type))return finish("The Mac sent an unexpected reply.");
        if(!strcmp(type->valuestring,"incomplete"))return finish("The agent could not explain this session.");
        if(strcmp(type->valuestring,"analysis_reply") || !cJSON_IsString(id) || strcmp(id->valuestring,request_id) ||
           !cJSON_IsString(text) || !text->valuestring[0] || strlen(text->valuestring)>2048)
            return finish("The Mac sent an unexpected reply.");
        out.text=text->valuestring;
    }
    replied=esp_timer_get_time();
    progress(nullptr,out.transcript.c_str(),out.text.c_str());
    if(p->speech_output()){speak(socket,*p,request_id);out.spoke=true;}
    return finish(nullptr);
}
