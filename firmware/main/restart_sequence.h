#pragma once
#include <cstdint>

// Plain retained data, with no constructor: RTC storage survives esp_restart.
// This is a bounded diagnostic sequence, never a recovery/reboot watchdog.
struct RestartSequence {
    void clear() { *this = {}; }
    void start(uint32_t id) {
        magic = tag; series_id = id; count = 0; pending = 0; seal();
    }
    bool resume(bool software_reset) {
        if (!software_reset || !valid() || pending != 1 || count == 0) {
            clear(); return false;
        }
        pending = 0; seal(); return true;
    }
    unsigned next() {
        if (!valid() || pending || count >= 10) { clear(); return 0; }
        ++count; pending = 1; seal(); return count;
    }
    unsigned completed() const { return valid() ? count : 0; }
    uint32_t series() const { return valid() ? series_id : 0; }
private:
    static constexpr uint32_t tag = 0x72535431;
    uint32_t magic, series_id, count, pending, checksum;
    uint32_t digest() const { return magic ^ series_id ^ (count * 0x9e3779b9U) ^ (pending * 0x85ebca6bU); }
    void seal() { checksum = digest(); }
    bool valid() const { return magic == tag && count <= 10 && pending <= 1 && checksum == digest(); }
};
