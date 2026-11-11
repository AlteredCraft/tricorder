#pragma once
#include <cstdlib>
#include <cstring>
// Finding the Mac service on a shared Wi-Fi network (no typed address). The device
// broadcasts the request on UDP to the service port; the service answers from its address
// on that network. Mirror of tools/service_discovery.py.
constexpr const char discovery_request[]="TRICORDER_DISCOVER 1\n";
// The WebSocket port in "TRICORDER_SERVICE 1 <port>[\n]", or 0 when text is not that.
inline int discovery_reply_port(const char* text) {
    constexpr const char prefix[]="TRICORDER_SERVICE 1 ";
    if(!text || strncmp(text,prefix,sizeof(prefix)-1))return 0;
    const char* digits=text+sizeof(prefix)-1;
    if(*digits<'0' || *digits>'9')return 0;
    char* end;const long port=strtol(digits,&end,10);
    if((*end && strcmp(end,"\n")) || port<1 || port>65535)return 0;
    return static_cast<int>(port);
}
