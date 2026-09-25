#pragma once
#include <cmath>
#include <cstdint>
#include "cJSON.h"

// Single media-owner reducer. UI communicates through a bounded queue and an
// atomic cancel flag; it never touches this object. No remote capture commands.
class InvestigationProtocol {
public:
    enum class State { Idle, Connecting, ReadyA, Asking, Transcribing, Confirming,
                       RecordingA, Uploading, Waiting, Acknowledging, Adjust, ReadyB,
                       RecordingB, ReturnA, RecordingRepeat, Complete, Cancelled, Offline, Incomplete };
    static constexpr unsigned max_questions=5,max_question_frames=128000;
    InvestigationProtocol(const char* boot, const char* session, unsigned frames=144000);
    ~InvestigationProtocol();
    InvestigationProtocol(const InvestigationProtocol&)=delete;
    InvestigationProtocol& operator=(const InvestigationProtocol&)=delete;
    bool ask(uint64_t now);
    bool start_capture();
    // Spoken ask (ADR-0013), only at ReadyA before Record A. The question audio is
    // its own buffer; only its identity is kept here. The host transcribes it and
    // the operator must Use or Retry a heard transcript before Record A.
    bool start_question();
    bool question_recorded(const cJSON* metadata,uint64_t now);
    cJSON* confirm_question(bool accepted);
    bool speech_available() const {return speech_;}
    bool speech_output() const {return voice_;} // the host can speak guidance
    unsigned questions_left() const {return speech_?max_questions-questions_:0;}
    const char* question_id() const {return question_id_;}
    const char* transcript() const {return transcript_;}
    const char* transcript_status() const {return status_;} // heard, empty, failed or ""
    const char* question() const {return question_;}
    double speech_to_noise_db() const {return speech_to_noise_db_;}
    bool captured(const cJSON* metadata, const cJSON* measurement, uint64_t now);
    cJSON* turn(uint64_t now); // Only after the caller checks the complete hash ACK.
    // After B's hash ACK: walk back to A and record it again before the compare
    // turn, which then joins A, B and A again (SD replay of a pair skips this).
    bool await_repeat();
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
    const char* boot() const {return boot_;}
    const char* session() const {return session_;}
    bool same_session(const cJSON* message) const;
    static cJSON* parse(const char* wire); // strict bounded JSON; caller owns
private:
    State state_=State::Idle;
    char boot_[97]{},session_[97]{},text_[2049]{},adjustment_[513]{};
    char question_id_[97]{},transcript_[513]{},question_[513]{},status_[8]{};
    bool speech_=false,voice_=false;
    unsigned questions_=0;
    double speech_to_noise_db_=NAN;
    unsigned frames_,count_=0;
    uint64_t deadline_=0;
    cJSON* captures_[3]{};
    cJSON* measurements_[3]{};
    bool ack_sent_=false;
};
