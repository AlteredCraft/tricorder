#include "investigation_protocol.h"
#include <cmath>
#include <cstring>
#include <cstdio>
#include <initializer_list>

namespace {
const cJSON* field(const cJSON* o,const char* key) {return cJSON_GetObjectItemCaseSensitive(o,key);}
bool str(const cJSON* v,const char* expected) {return cJSON_IsString(v) && !strcmp(v->valuestring,expected);}
bool number(const cJSON* v,double expected) {return cJSON_IsNumber(v) && v->valuedouble==expected;}
bool bounded(const cJSON* v,size_t limit) {
    if(!cJSON_IsString(v))return false;
    size_t n=strlen(v->valuestring);if(!n || n>limit)return false;
    for(size_t i=0;i<n;++i)if(static_cast<unsigned char>(v->valuestring[i])>32)return true;
    return false;
}
bool id(const char* s) {
    if(!s || !*s || strlen(s)>96)return false;
    for(;*s;++s)if(!((*s>='a' && *s<='z') || (*s>='A' && *s<='Z') ||
                    (*s>='0' && *s<='9') || *s=='_' || *s=='-'))return false;
    return true;
}
bool integer(const cJSON* n,double lo,double hi) {
    return cJSON_IsNumber(n) && std::isfinite(n->valuedouble) &&
        n->valuedouble>=lo && n->valuedouble<=hi && floor(n->valuedouble)==n->valuedouble;
}
bool shape(const cJSON* node,unsigned depth,unsigned& budget) {
    if(!node || depth>12 || !budget--)return false;
    if(cJSON_IsNumber(node) && !std::isfinite(node->valuedouble))return false;
    for(auto* c=node->child;c;c=c->next) {
        if(cJSON_IsObject(node)) {
            if(!c->string)return false;
            for(auto* d=node->child;d!=c;d=d->next)if(!strcmp(c->string,d->string))return false;
        }
        if(!shape(c,depth+1,budget))return false;
    }
    return true;
}
bool close_number(const cJSON* a,const cJSON* b) {
    if(cJSON_IsNull(a) || cJSON_IsNull(b))return cJSON_IsNull(a) && cJSON_IsNull(b);
    return cJSON_IsNumber(a) && cJSON_IsNumber(b) && std::isfinite(a->valuedouble) &&
        std::isfinite(b->valuedouble) && fabs(a->valuedouble-b->valuedouble)<=1e-8*std::fmax(1.,fabs(b->valuedouble));
}
bool measurement(const cJSON* m,unsigned frames) {
    if(!cJSON_IsObject(m) || cJSON_GetArraySize(m)!=5 || !number(field(m,"frames"),frames) ||
       !integer(field(m,"peak_counts"),0,32768) || !integer(field(m,"clipped_samples"),0,frames))return false;
    auto* rms=field(m,"rms_counts");auto* peak=field(m,"peak_counts");auto* db=field(m,"rms_dbfs");
    if(!cJSON_IsNumber(rms) || !std::isfinite(rms->valuedouble) || rms->valuedouble<0 || rms->valuedouble>peak->valuedouble)return false;
    if(rms->valuedouble==0)return cJSON_IsNull(db);
    return cJSON_IsNumber(db) && std::isfinite(db->valuedouble) && fabs(db->valuedouble-20*log10(rms->valuedouble/32768))<1e-8;
}
}

InvestigationProtocol::InvestigationProtocol(const char* boot,const char* session,unsigned frames):frames_(frames) {
    if(!id(boot) || !id(session) || !frames || frames>144000){state_=State::Incomplete;return;}
    strcpy(boot_,boot);strcpy(session_,session);
}
InvestigationProtocol::~InvestigationProtocol() {for(auto* p:captures_)cJSON_Delete(p);for(auto* p:measurements_)cJSON_Delete(p);}
cJSON* InvestigationProtocol::parse(const char* wire) {
    if(!wire || strlen(wire)>32768)return nullptr;
    // cJSON represents strings as C strings: reject escaped NUL to prevent
    // a value/key being truncated to a different identity by that parser.
    for(const char* p=wire;*p;++p)if(*p=='\\') {
        ++p;if(!*p)return nullptr;
        if(*p=='u' && !strncmp(p,"u0000",5))return nullptr;
    }
    auto* o=cJSON_ParseWithOpts(wire,nullptr,true);unsigned budget=512;
    if(!cJSON_IsObject(o) || !shape(o,0,budget)){cJSON_Delete(o);return nullptr;}return o;
}
cJSON* InvestigationProtocol::envelope(const char* type) const {
    auto* o=cJSON_CreateObject();cJSON_AddNumberToObject(o,"version",1);
    cJSON_AddStringToObject(o,"type",type);cJSON_AddStringToObject(o,"boot_id",boot_);
    cJSON_AddStringToObject(o,"session_id",session_);return o;
}
bool InvestigationProtocol::same_session(const cJSON* o) const {
    return number(field(o,"version"),1) && str(field(o,"boot_id"),boot_) && str(field(o,"session_id"),session_);
}
bool InvestigationProtocol::ask(uint64_t now) {
    if(state_!=State::Idle)return false;
    state_=State::Connecting;deadline_=now+15000;return true;
}
bool InvestigationProtocol::start_capture() {
    if(state_==State::ReadyA)state_=State::RecordingA;
    else if(state_==State::ReadyB)state_=State::RecordingB;
    else if(state_==State::ReturnA)state_=State::RecordingRepeat;
    else return false;
    return true;
}
bool InvestigationProtocol::start_question() {
    if(state_!=State::ReadyA || !speech_ || questions_>=max_questions)return false;
    state_=State::Asking;return true;
}
bool InvestigationProtocol::question_recorded(const cJSON* m,uint64_t now) {
    if(state_!=State::Asking)return false;
    auto* key=field(m,"question_id");auto* hash=field(m,"sha256");auto* frames=field(m,"frames");
    if(!str(field(m,"boot_id"),boot_) || !str(field(m,"session_id"),session_) ||
       !cJSON_IsString(key) || !id(key->valuestring) || !strcmp(key->valuestring,question_id_) ||
       !cJSON_IsString(hash) || strlen(hash->valuestring)!=64 || !str(field(m,"format"),"pcm_s16le") ||
       !number(field(m,"sample_rate_hz"),16000) || !number(field(m,"channels"),1) ||
       !integer(frames,1,max_question_frames) || !number(field(m,"size_bytes"),frames->valuedouble*2) ||
       !cJSON_IsTrue(field(m,"driver_epoch_integrity")) ||
       !integer(field(m,"acquisition_start_us"),0,9007199254740990.) ||
       !integer(field(m,"acquisition_end_us"),field(m,"acquisition_start_us")->valuedouble+1,9007199254740991.))return false;
    for(const char* p=hash->valuestring;*p;++p)if(!((*p>='0' && *p<='9') || (*p>='a' && *p<='f')))return false;
    strcpy(question_id_,key->valuestring);transcript_[0]=status_[0]=0;speech_to_noise_db_=NAN;++questions_;
    deadline_=now+30000;state_=State::Transcribing;return true;
}
cJSON* InvestigationProtocol::confirm_question(bool accepted) {
    if(state_!=State::Confirming)return nullptr;
    if(accepted)strcpy(question_,transcript_);
    auto* o=envelope("question_confirm");cJSON_AddStringToObject(o,"question_id",question_id_);
    cJSON_AddBoolToObject(o,"accepted",accepted);state_=State::ReadyA;return o;
}
bool InvestigationProtocol::captured(const cJSON* m,const cJSON* v,uint64_t now) {
    if((state_!=State::RecordingA && state_!=State::RecordingB && state_!=State::RecordingRepeat) || count_>=3)return false;
    auto* key=field(m,"capture_id");auto* hash=field(m,"sha256");
    if(!str(field(m,"boot_id"),boot_) || !str(field(m,"session_id"),session_) ||
       !cJSON_IsString(key) || !id(key->valuestring) || !cJSON_IsString(hash) || strlen(hash->valuestring)!=64 ||
       !str(field(m,"format"),"pcm_s16le") || !number(field(m,"sample_rate_hz"),48000) ||
       !number(field(m,"channels"),4) || !number(field(m,"frames"),frames_) ||
       !number(field(m,"size_bytes"),frames_*8) || !number(field(m,"gain_db"),24) ||
       !number(field(m,"source_slot"),0) || !str(field(m,"physical_slot"),"farther-hole") ||
       !cJSON_IsTrue(field(m,"driver_epoch_integrity")) || !cJSON_IsFalse(field(m,"speaker_active")) ||
       !integer(field(m,"acquisition_start_us"),0,9007199254740990.) ||
       !integer(field(m,"acquisition_end_us"),field(m,"acquisition_start_us")->valuedouble+1,9007199254740991.) ||
       !measurement(v,frames_))return false;
    for(const char* p=hash->valuestring;*p;++p)if(!((*p>='0' && *p<='9') || (*p>='a' && *p<='f')))return false;
    if(!strcmp(key->valuestring,question_id_))return false;
    for(unsigned i=0;i<count_;++i)if(!strcmp(key->valuestring,capture_id(i)))return false;
    if(count_ && field(m,"acquisition_start_us")->valuedouble<field(captures_[count_-1],"acquisition_end_us")->valuedouble)return false;
    // Raw capture ownership retains the full ingress proof through SD commit
    // and upload ACK. The reducer only needs identity and the previous end
    // timestamp; copying 141 proof blocks here consumed ~62 KiB per capture
    // and starved hosted Wi-Fi's DMA heap while saving B to SD.
    auto* meta=cJSON_CreateObject();auto* values=cJSON_Duplicate(v,true);
    if(!meta || !values || !cJSON_AddStringToObject(meta,"capture_id",key->valuestring) ||
       !cJSON_AddNumberToObject(meta,"acquisition_end_us",field(m,"acquisition_end_us")->valuedouble)) {
        cJSON_Delete(meta);cJSON_Delete(values);fail();return false;
    }
    captures_[count_]=meta;measurements_[count_]=values;++count_;
    deadline_=now+30000;state_=State::Uploading;return true;
}
const char* InvestigationProtocol::capture_id(unsigned index) const {
    return index<count_ ? field(captures_[index],"capture_id")->valuestring : "";
}
bool InvestigationProtocol::await_repeat() {
    if(state_!=State::Uploading || count_!=2)return false;
    state_=State::ReturnA;deadline_=0;return true;
}
cJSON* InvestigationProtocol::turn(uint64_t now) {
    tick(now);if(state_!=State::Uploading)return nullptr;
    auto* o=envelope("turn");cJSON_AddStringToObject(o,"request_id",count_==1?"r1":"r2");
    auto* ids=cJSON_AddArrayToObject(o,"capture_ids");
    for(unsigned i=0;i<count_;++i)cJSON_AddItemToArray(ids,cJSON_CreateString(capture_id(i)));
    deadline_=now+15000;cJSON_AddNumberToObject(o,"device_ms",now);cJSON_AddNumberToObject(o,"deadline_ms",deadline_);
    if(count_>1)cJSON_AddStringToObject(o,"adjustment",adjustment_);
    state_=State::Waiting;return o;
}
bool InvestigationProtocol::receive(const char* wire,uint64_t now) {
    tick(now);auto* o=parse(wire);if(!o)return false;
    bool ok=false;
    if(same_session(o)) {
        auto* speech=field(o,"speech_to_text");
        if(state_==State::Connecting && str(field(o,"type"),"ready") && cJSON_GetArraySize(o)==6 && bounded(field(o,"provider"),96) &&
           (cJSON_IsNull(speech) || bounded(speech,96))) {
            speech_=!cJSON_IsNull(speech);state_=State::ReadyA;deadline_=0;ok=true;
        } else if(state_==State::Transcribing && str(field(o,"type"),"transcript") && cJSON_GetArraySize(o)==8 &&
                  str(field(o,"question_id"),question_id_)) {
            // Heard text needs Use or Retry; nothing heard or a failed engine returns to Record A.
            auto* status=field(o,"status");auto* words=field(o,"text");auto* level=field(o,"speech_to_noise_db");
            const bool heard=str(status,"heard");
            ok=(heard || str(status,"empty") || str(status,"failed")) &&
                (heard ? bounded(words,512) : str(words,"")) &&
                (cJSON_IsNull(level) || (cJSON_IsNumber(level) && std::isfinite(level->valuedouble) && fabs(level->valuedouble)<=200));
            if(ok) {
                if(heard)strcpy(transcript_,words->valuestring);
                strcpy(status_,status->valuestring);
                speech_to_noise_db_=cJSON_IsNumber(level)?level->valuedouble:NAN;
                state_=heard?State::Confirming:State::ReadyA;deadline_=0;
            }
        } else if(state_==State::Acknowledging && ack_sent_ && str(field(o,"type"),"acknowledged") && cJSON_GetArraySize(o)==6 &&
                  str(field(o,"request_id"),count_==1?"r1":"r2") && str(field(o,"state"),count_==1?"adjust":"complete")) {
            state_=count_==1?State::Adjust:State::Complete;deadline_=0;ok=true;
        } else if(state_==State::Waiting && cJSON_GetArraySize(o)==10 &&
                  str(field(o,"type"),count_==1?"guidance":"comparison") &&
                  str(field(o,"request_id"),count_==1?"r1":"r2") && number(field(o,"deadline_ms"),deadline_) &&
                  bounded(field(o,"text"),2048)) {
            auto* ids=field(o,"capture_ids");auto* values=field(o,"measurements");
            ok=cJSON_IsArray(ids) && cJSON_IsArray(values) &&
                cJSON_GetArraySize(ids)==static_cast<int>(count_) && cJSON_GetArraySize(values)==static_cast<int>(count_);
            for(unsigned i=0;ok && i<count_;++i) {
                auto* m=cJSON_GetArrayItem(values,i);ok=str(cJSON_GetArrayItem(ids,i),capture_id(i)) && measurement(m,frames_);
                for(const char* key:{"frames","rms_counts","peak_counts","clipped_samples","rms_dbfs"})
                    ok=ok && close_number(field(m,key),field(measurements_[i],key));
            }
            auto* compare=field(o,"comparison");
            if(count_==1)ok=ok && cJSON_IsNull(compare);
            else {
                // B/A, and A-again/A when repeated; null when any capture clipped or was silent.
                bool valid=true;
                for(unsigned i=0;i<count_;++i)valid=valid && field(measurements_[i],"rms_counts")->valuedouble>0 &&
                    number(field(measurements_[i],"clipped_samples"),0);
                const double a=field(measurements_[0],"rms_counts")->valuedouble;
                auto matches=[&](const cJSON* v,unsigned index)->bool {
                    if(!valid || index>=count_)return cJSON_IsNull(v);
                    return cJSON_IsNumber(v) && fabs(v->valuedouble-20*log10(field(measurements_[index],"rms_counts")->valuedouble/a))<1e-8;
                };
                ok=ok && cJSON_IsObject(compare) && cJSON_GetArraySize(compare)==4 &&
                    str(field(compare,"status"),valid?"measured":"inconclusive") &&
                    str(field(compare,"unit"),"digital RMS dB ratio; not calibrated SPL") &&
                    matches(field(compare,"rms_delta_db"),1) && field(compare,"repeat_delta_db") &&
                    matches(field(compare,"repeat_delta_db"),2);
            }
            if(ok){strcpy(text_,field(o,"text")->valuestring);state_=State::Acknowledging;ack_sent_=false;}
        }
    }
    cJSON_Delete(o);return ok;
}
cJSON* InvestigationProtocol::ack() {
    if(state_!=State::Acknowledging || ack_sent_)return nullptr;
    ack_sent_=true;
    auto* o=envelope("ack");cJSON_AddStringToObject(o,"request_id",count_==1?"r1":"r2");return o;
}
bool InvestigationProtocol::adjust(const char* text) {
    if(state_!=State::Adjust || !text || !*text || strlen(text)>512)return false;
    strcpy(adjustment_,text);state_=State::ReadyB;return true;
}
void InvestigationProtocol::tick(uint64_t now) {if(deadline_ && now>=deadline_ && !terminal())fail();}
bool InvestigationProtocol::terminal() const {return state_==State::Complete || state_==State::Cancelled || state_==State::Offline || state_==State::Incomplete;}
void InvestigationProtocol::cancel() {if(state_!=State::Complete){state_=State::Cancelled;deadline_=0;}}
void InvestigationProtocol::disconnect() {if(!terminal()){state_=State::Offline;deadline_=0;}}
void InvestigationProtocol::fail() {if(!terminal()){state_=State::Incomplete;deadline_=0;}}
const char* InvestigationProtocol::state_name() const {
    static const char* names[]={"idle","connecting","ready_a","asking","transcribing","confirming","recording_a","uploading","waiting",
                                "acknowledging","adjust","ready_b","recording_b","return_a","recording_repeat","complete","cancelled","offline","incomplete"};
    return names[static_cast<unsigned>(state_)];
}
