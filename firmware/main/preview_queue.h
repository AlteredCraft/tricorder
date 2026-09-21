#pragma once
#include <atomic>
#include <cassert>
#include <cstddef>
#include <cstdint>

// One producer, one renderer. Slot storage belongs to the caller and must
// outlive the queue. The renderer releases its old source only between draws.
class PreviewQueue {
public:
    int begin_write() {
        for (int i=0;i<3;++i) {
            unsigned expected=free;
            if (slots_[i].state.compare_exchange_strong(expected,writing,std::memory_order_acquire)) return i;
        }
        return -1;
    }
    void cancel_write(int i) {
        assert(i>=0 && i<3 && slots_[i].state.load()==writing);
        slots_[i].state.store(free,std::memory_order_release);
    }
    void publish(int i,uint32_t generation) {
        assert(i>=0 && i<3 && slots_[i].state.load()==writing);
        slots_[i].generation=generation;
        slots_[i].state.store(queued,std::memory_order_release);
        const int old=pending_.exchange(i,std::memory_order_acq_rel);
        if (old>=0) {slots_[old].state.store(free,std::memory_order_release);++replaced_;}
        ++produced_;
    }
    int take_latest() {
        const int next=pending_.exchange(-1,std::memory_order_acq_rel);
        if (next<0) return -1;
        if (displayed_>=0) slots_[displayed_].state.store(free,std::memory_order_release);
        slots_[next].state.store(displayed,std::memory_order_release);
        displayed_=next;++selected_;return next;
    }
    void release_display() {
        if (displayed_>=0) slots_[displayed_].state.store(free,std::memory_order_release);
        displayed_=-1;
    }
    uint32_t generation(int i) const {assert(i>=0 && i<3);return slots_[i].generation;}
    unsigned pending() const {return pending_.load(std::memory_order_acquire)>=0 ? 1:0;}
    // Read counters after producer and renderer have quiesced.
    uint32_t produced() const {return produced_;}
    uint32_t selected() const {return selected_;}
    uint32_t replaced() const {return replaced_;}
private:
    enum : unsigned {free,writing,queued,displayed};
    struct Slot {std::atomic<unsigned> state{free};uint32_t generation=0;} slots_[3];
    std::atomic<int> pending_{-1};int displayed_=-1;
    uint32_t produced_=0,replaced_=0,selected_=0;
};

inline bool preview_half_rgb565(const uint16_t* source,size_t source_bytes,unsigned width,unsigned height,
                               uint16_t* output,size_t output_bytes) {
    if (!source || !output || !width || !height || width>1600 || height>1600 || width%2 || height%2
        || source_bytes!=size_t(width)*height*2 || output_bytes!=size_t(width/2)*(height/2)*2) return false;
    for (unsigned y=0;y<height/2;++y)
        for (unsigned x=0;x<width/2;++x) output[size_t(y)*(width/2)+x]=source[size_t(y*2)*width+x*2];
    return true;
}
