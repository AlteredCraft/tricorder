#pragma once
#include <cstdint>

// LVGL timers reset their phase to the actual callback time. Compensate for
// tick rounding against absolute device time so lateness does not accumulate.
class UiSchedule {
public:
    explicit UiSchedule(int64_t epoch):next_(epoch+33000) {}
    uint32_t after_tick(int64_t now) {
        next_+=33000;
        while (next_<=now) {next_+=33000;++missed_;}
        return uint32_t((next_-now+999)/1000);
    }
    uint64_t missed() const {return missed_;}
private:
    int64_t next_;uint64_t missed_=0;
};
