#pragma once
#include <cstdint>
#include "cJSON.h"

// Single media-owner reducer. UI communicates through a bounded queue and an
// atomic cancel flag; it never touches this object. No remote capture commands.
class InvestigationProtocol {
public:
    enum class State { Idle, Connecting, ReadyA, RecordingA, Uploading, Waiting,
                       Acknowledging, Adjust, ReadyB, RecordingB, Complete,
                       Cancelled, Offline, Incomplete };
    InvestigationProtocol(const char* boot, const char* session, unsigned frames=144000);
    ~InvestigationProtocol();
    InvestigationProtocol(const InvestigationProtocol&)=delete;
    InvestigationProtocol& operator=(const InvestigationProtocol&)=delete;
    bool ask(uint64_t now);
    bool start_capture();
    bool captured(const cJSON* metadata, const cJSON* measurement, uint64_t now);
    cJSON* turn(uint64_t now); // Only after the caller checks the complete hash ACK.
    bool receive(const char* wire, uint64_t now);
    cJSON* ack();
    bool adjust(const char* text);
    void tick(uint64_t now);
    void cancel();
    void disconnect();
    void fail();
    bool terminal() const;
    State state() const {return state_;}
    const char* state_name() const;
    const char* text() const {return text_;}
    const char* capture_id(unsigned index) const;
    cJSON* envelope(const char* type) const;
    bool same_session(const cJSON* message) const;
    static cJSON* parse(const char* wire); // strict bounded JSON; caller owns
private:
    State state_=State::Idle;
    char boot_[97]{},session_[97]{},text_[2049]{},adjustment_[513]{};
    unsigned frames_,count_=0;
    uint64_t deadline_=0;
    cJSON* captures_[2]{};
    cJSON* measurements_[2]{};
    bool ack_sent_=false;
};
