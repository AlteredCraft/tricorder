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
    void reset() {memset(bins_,0,sizeof(bins_));count_=0;max_=0;last_=-1;}
    void tick(int64_t now_us) {
        if(last_>=0) {
            const int64_t us=now_us-last_;
            const int64_t ms=(us+999)/1000;
            ++bins_[ms>1000?1001:ms<0?0:ms];++count_;
            if(us>max_)max_=us;
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
private:
    uint32_t bins_[1002]{};
    uint64_t count_=0;
    int64_t max_=0,last_=-1;
};
