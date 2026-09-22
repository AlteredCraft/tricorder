#pragma once
#include <cstring>
#include <cstddef>
#include <initializer_list>

inline bool investigation_replay_session(const char* id) {
    if(!id || strlen(id)!=35 || strncmp(id,"ab-",3))return false;
    for(const char* p=id+3;*p;++p)if(!((*p>='0' && *p<='9') || (*p>='a' && *p<='f')))return false;
    return true;
}

// Experiment LAN endpoint only; explicit ws://host:port/path, no credentials,
// query, fragments or IPv6. Nothing is persisted and no cloud keys reach device.
struct InvestigationEndpoint {
    char host[97]{},path[129]{};
    int port=0;
    bool parse(const char* uri) {
        if(!uri || strlen(uri)>240 || strncmp(uri,"ws://",5))return false;
        const char* p=uri+5;const char* start=p;
        while((*p>='a' && *p<='z') || (*p>='A' && *p<='Z') || (*p>='0' && *p<='9') || *p=='.' || *p=='-')++p;
        size_t n=p-start;if(!n || n>96 || *p++!=':')return false;
        memcpy(host,start,n);host[n]=0;port=0;const char* digits=p;
        while(*p>='0' && *p<='9') {port=port*10+(*p++-'0');if(port>65535)return false;}
        if(p==digits || !port || (*p && *p!='/'))return false;
        if(!*p)p="/";
        if(strlen(p)>128)return false;
        for(const char* q=p;*q;++q)if(!((*q>='a' && *q<='z') || (*q>='A' && *q<='Z') ||
            (*q>='0' && *q<='9') || *q=='/' || *q=='-' || *q=='_' || *q=='.'))return false;
        strcpy(path,p);return true;
    }
};

// Input is one esp_transport_read payload segment. Control frames are handled
// by the transport and never passed here. Supports split reads and continuation
// frames without allocating from lengths supplied by the peer.
class InvestigationFrames {
public:
    explicit InvestigationFrames(char* storage):data_(storage) {reset();}
    void reset() {used_=remaining_=0;fragmented_=false;done_=false;data_[0]=0;}
    int append(int opcode,int payload,bool fin,const char* bytes,size_t size) {
        if(done_ || payload<=0 || payload>32768 || !size)return -1;
        if(!remaining_) {
            if((fragmented_ && opcode!=0) || (!fragmented_ && opcode!=1) || used_+payload>32768)return -1;
            remaining_=payload;opcode_=opcode;fin_=fin;payload_=payload;
        } else if(opcode!=opcode_ || fin!=fin_ || payload!=payload_)return -1;
        if(size>remaining_ || memchr(bytes,0,size))return -1;
        memcpy(data_+used_,bytes,size);used_+=size;remaining_-=size;data_[used_]=0;
        if(!remaining_) {fragmented_=!fin_;if(fin_){done_=true;return 1;}}
        return 0;
    }
private:
    char* data_;size_t used_=0,remaining_=0;
    int opcode_=0,payload_=0;bool fin_=false,fragmented_=false,done_=false;
};
