#pragma once
#include <atomic>
#include <cstdint>
#include <cstddef>
#include <cstring>

struct FrameStamp {
    uint64_t sequence=0;
    int64_t completed=0,dequeued=0,copied=0;
    int64_t source_hash_start=0,source_hash_end=0,copy_start=0;
    unsigned index=0;
    char source_sha256[65]{};
};
class OwnedFrame {
public:
    OwnedFrame(unsigned char* memory,size_t bytes):memory_(memory),bytes_(bytes) {}
    bool copy(const unsigned char* source,size_t bytes,const FrameStamp& stamp,int64_t(*clock)()=nullptr) {
        if (!source || !memory_ || bytes!=bytes_) return false;
        unsigned expected=0;
        if (!state_.compare_exchange_strong(expected,1,std::memory_order_acquire)) return false;
        memcpy(memory_,source,bytes_);stamp_=stamp;
        if (clock) stamp_.copied=clock();
        state_.store(2,std::memory_order_release);return true;
    }
    bool acquire(const unsigned char*& data,FrameStamp& stamp) {
        unsigned expected=2;
        if (!state_.compare_exchange_strong(expected,3,std::memory_order_acquire)) return false;
        data=memory_;stamp=stamp_;return true;
    }
    void release() {state_.store(0,std::memory_order_release);}
    bool idle() const {return state_.load(std::memory_order_acquire)==0;}
private:
    unsigned char* memory_;size_t bytes_;FrameStamp stamp_{};std::atomic<unsigned> state_{0};
};
