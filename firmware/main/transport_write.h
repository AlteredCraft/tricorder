#pragma once
#include <cstdint>

// Complete one already-framed range on the TCP parent, without resending a
// WebSocket header or restarting its masking sequence after a partial send.
// Zero/error/cancel/expiry invalidate the connection; callers must close it.
template<class Write, class Clock, class Cancel>
int transport_write_all(const char* data,int size,int timeout_ms,
                        Write write,Clock clock,Cancel cancel) {
    if(!data || size<0 || timeout_ms<=0)return -1;
    const uint64_t start=clock();
    int offset=0;
    while(offset<size) {
        const uint64_t elapsed=clock()-start;
        if(cancel() || elapsed>=static_cast<uint64_t>(timeout_ms))return -1;
        const int count=write(data+offset,size-offset,timeout_ms-static_cast<int>(elapsed));
        if(count<=0 || count>size-offset)return -1;
        offset+=count;
    }
    return offset;
}
