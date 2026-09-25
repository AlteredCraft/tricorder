#pragma once
#include <cstdint>
#include <cstring>

// Intervals between runs of a periodic LVGL probe timer (G-0001.02 C2). The
// probe runs inside lv_timer_handler, so a long render or a held display lock
// shows up as a long interval. Bins are whole milliseconds, rounded up, to 1 s;
// longer intervals share bin 1001 and set max_us(). One owner: LVGL callbacks
// and readers both hold the display lock.
class UiPulse {
public:
    struct Long {int64_t end_us,duration_us;};
    static constexpr unsigned long_capacity=8;
    void reset() {memset(bins_,0,sizeof(bins_));count_=0;max_=0;last_=-1;longs_=0;}
    void tick(int64_t now_us) {
        if(last_>=0) {
            const int64_t us=now_us-last_;
            const int64_t ms=(us+999)/1000;
            ++bins_[ms>1000?1001:ms<0?0:ms];++count_;
            if(us>max_)max_=us;
            // Keep the last few stalls so they can be matched to device events.
            if(us>200000)long_[longs_++%long_capacity]={now_us,us};
        }
        last_=now_us;
    }
    uint64_t count() const {return count_;}
    int64_t max_us() const {return max_;}
    // Smallest whole-ms bin covering fraction q of the intervals (1001 = over 1 s).
    unsigned percentile_ms(double q) const {
        if(!count_)return 0;
        const double need=q*static_cast<double>(count_);uint64_t seen=0;
        for(unsigned ms=0;ms<=1001;++ms) {
            seen+=bins_[ms];
            if(static_cast<double>(seen)>=need)return ms;
        }
        return 1001;
    }
    uint64_t over_ms(unsigned ms) const {
        uint64_t n=0;
        for(unsigned i=ms+1;i<=1001;++i)n+=bins_[i];
        return n;
    }
    unsigned long_count() const {return longs_<long_capacity?longs_:long_capacity;}
    // i = 0 is the oldest one kept.
    Long long_at(unsigned i) const {return long_[(longs_-long_count()+i)%long_capacity];}
private:
    Long long_[long_capacity]{};
    unsigned longs_=0;
    uint32_t bins_[1002]{};
    uint64_t count_=0;
    int64_t max_=0,last_=-1;
};
