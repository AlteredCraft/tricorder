#include "service_protocol.h"
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
}

ServiceProtocol::ServiceProtocol(const char* boot,const char* session) {
    if(!id(boot) || !id(session)){state_=State::Incomplete;return;}
    strcpy(boot_,boot);strcpy(session_,session);
}
cJSON* ServiceProtocol::parse(const char* wire) {
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
cJSON* ServiceProtocol::envelope(const char* type) const {
    auto* o=cJSON_CreateObject();cJSON_AddNumberToObject(o,"version",1);
    cJSON_AddStringToObject(o,"type",type);cJSON_AddStringToObject(o,"boot_id",boot_);
    cJSON_AddStringToObject(o,"session_id",session_);return o;
}
bool ServiceProtocol::same_session(const cJSON* o) const {
    return number(field(o,"version"),1) && str(field(o,"boot_id"),boot_) && str(field(o,"session_id"),session_);
}
bool ServiceProtocol::ask(uint64_t now) {
    if(state_!=State::Idle)return false;
    state_=State::Connecting;deadline_=now+15000;return true;
}
bool ServiceProtocol::start_question() {
    if(state_!=State::Ready || !speech_ || questions_>=max_questions)return false;
    state_=State::Asking;return true;
}
bool ServiceProtocol::question_recorded(const cJSON* m,uint64_t now) {
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
cJSON* ServiceProtocol::confirm_question(bool accepted) {
    if(state_!=State::Confirming)return nullptr;
    auto* o=envelope("question_confirm");cJSON_AddStringToObject(o,"question_id",question_id_);
    cJSON_AddBoolToObject(o,"accepted",accepted);state_=State::Ready;return o;
}
bool ServiceProtocol::receive(const char* wire,uint64_t now) {
    tick(now);auto* o=parse(wire);if(!o)return false;
    bool ok=false;
    if(same_session(o)) {
        auto* speech=field(o,"speech_to_text");auto* voice=field(o,"speech_output");
        if(state_==State::Connecting && str(field(o,"type"),"ready") && cJSON_GetArraySize(o)==7 && bounded(field(o,"provider"),96) &&
           (cJSON_IsNull(speech) || bounded(speech,96)) && (cJSON_IsNull(voice) || bounded(voice,96))) {
            speech_=!cJSON_IsNull(speech);voice_=!cJSON_IsNull(voice);state_=State::Ready;deadline_=0;ok=true;
        } else if(state_==State::Transcribing && str(field(o,"type"),"transcript") && cJSON_GetArraySize(o)==8 &&
                  str(field(o,"question_id"),question_id_)) {
            // Heard text needs confirming; nothing heard or a failed engine returns to Ready.
            auto* status=field(o,"status");auto* words=field(o,"text");auto* level=field(o,"speech_to_noise_db");
            const bool heard=str(status,"heard");
            ok=(heard || str(status,"empty") || str(status,"failed")) &&
                (heard ? bounded(words,512) : str(words,"")) &&
                (cJSON_IsNull(level) || (cJSON_IsNumber(level) && std::isfinite(level->valuedouble) && fabs(level->valuedouble)<=200));
            if(ok) {
                if(heard)strcpy(transcript_,words->valuestring);
                strcpy(status_,status->valuestring);
                speech_to_noise_db_=cJSON_IsNumber(level)?level->valuedouble:NAN;
                state_=heard?State::Confirming:State::Ready;deadline_=0;
            }
        }
    }
    cJSON_Delete(o);return ok;
}
void ServiceProtocol::tick(uint64_t now) {if(deadline_ && now>=deadline_ && !terminal())fail();}
bool ServiceProtocol::terminal() const {return state_==State::Offline || state_==State::Incomplete;}
void ServiceProtocol::disconnect() {if(!terminal()){state_=State::Offline;deadline_=0;}}
void ServiceProtocol::fail() {if(!terminal()){state_=State::Incomplete;deadline_=0;}}
const char* ServiceProtocol::state_name() const {
    static const char* names[]={"idle","connecting","ready","asking","transcribing","confirming","offline","incomplete"};
    return names[static_cast<unsigned>(state_)];
}
