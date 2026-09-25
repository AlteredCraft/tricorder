#pragma once
#include <cstddef>
#include <cstdint>
#include <cstring>
#include "cJSON.h"

// Spoken guidance from the Mac (ADR-0014): speech_start, speech_chunk xN,
// speech_end for one requested reply. Validates each message and decodes its
// 24 kHz mono s16le audio into a caller-owned buffer; playback reads frames()
// as they grow. Anything out of order, oversized or malformed is an error.
class SpeechStream {
public:
    SpeechStream(const char* boot,const char* session,int16_t* buffer,size_t capacity)
        :boot_(boot),session_(session),buffer_(buffer),capacity_(capacity) {}
    void begin(const char* request_id) {
        strncpy(request_,request_id,sizeof(request_)-1);request_[sizeof(request_)-1]=0;
        started_=ended_=false;frames_=0;status_[0]=0;
    }
    // 0: more expected, 1: ended (status() says how), -1: protocol error.
    int receive(const cJSON* o) {
        if(ended_ || !cJSON_IsObject(o) || !match(o,"boot_id",boot_) || !match(o,"session_id",session_) ||
           !match(o,"request_id",request_))return -1;
        auto* version=cJSON_GetObjectItemCaseSensitive(o,"version");
        if(!cJSON_IsNumber(version) || version->valuedouble!=1)return -1;
        const int fields=cJSON_GetArraySize(o);
        if(match(o,"type","speech_start")) {
            if(started_ || fields!=8 || !match(o,"format","pcm_s16le") || !number(o,"sample_rate_hz",24000) ||
               !number(o,"channels",1))return -1;
            started_=true;return 0;
        }
        if(!started_)return -1;
        if(match(o,"type","speech_chunk")) {
            auto* data=cJSON_GetObjectItemCaseSensitive(o,"data");
            if(fields!=7 || !number(o,"offset",static_cast<double>(frames_)) || !cJSON_IsString(data))return -1;
            const size_t bytes=decode(data->valuestring);
            if(!bytes || bytes%2 || frames_+bytes/2>capacity_)return -1;
            frames_+=bytes/2;return 0;
        }
        if(match(o,"type","speech_end")) {
            auto* status=cJSON_GetObjectItemCaseSensitive(o,"status");
            if(fields!=7 || !number(o,"frames",static_cast<double>(frames_)) || !cJSON_IsString(status) ||
               (strcmp(status->valuestring,"complete") && strcmp(status->valuestring,"stopped") &&
                strcmp(status->valuestring,"failed")))return -1;
            strcpy(status_,status->valuestring);ended_=true;return 1;
        }
        return -1;
    }
    size_t frames() const {return frames_;}
    bool started() const {return started_;}
    bool ended() const {return ended_;}
    const char* status() const {return ended_?status_:"streaming";}
private:
    static bool match(const cJSON* o,const char* key,const char* value) {
        auto* v=cJSON_GetObjectItemCaseSensitive(o,key);return cJSON_IsString(v) && !strcmp(v->valuestring,value);
    }
    static bool number(const cJSON* o,const char* key,double value) {
        auto* v=cJSON_GetObjectItemCaseSensitive(o,key);return cJSON_IsNumber(v) && v->valuedouble==value;
    }
    // Strict base64 of at most 4096 bytes, written straight after the frames
    // already held; returns the decoded byte count, 0 on any error.
    size_t decode(const char* text) {
        const size_t n=strlen(text);
        if(!n || n%4 || n>5464)return 0;
        auto* out=reinterpret_cast<unsigned char*>(buffer_+frames_);
        const size_t room=(capacity_-frames_)*2;
        size_t written=0;
        for(size_t i=0;i<n;i+=4) {
            int v[4];
            for(int k=0;k<4;++k) {
                const char c=text[i+k];
                v[k]=c>='A' && c<='Z'?c-'A':c>='a' && c<='z'?c-'a'+26:c>='0' && c<='9'?c-'0'+52:
                     c=='+'?62:c=='/'?63:c=='=' && i+4==n && k>=2?-2:-1;
                if(v[k]==-1)return 0;
            }
            if(v[2]==-2 && v[3]!=-2)return 0;
            const int count=v[2]==-2?1:v[3]==-2?2:3;
            const unsigned bits=(v[0]<<18)|(v[1]<<12)|((v[2]<0?0:v[2])<<6)|(v[3]<0?0:v[3]);
            if(written+count>room)return 0;
            out[written++]=bits>>16;
            if(count>1)out[written++]=(bits>>8)&0xff;
            if(count>2)out[written++]=bits&0xff;
        }
        return written>4096?0:written;
    }
    const char *boot_,*session_;
    int16_t* buffer_;
    size_t capacity_,frames_=0;
    char request_[97]{},status_[9]{};
    bool started_=false,ended_=false;
};
