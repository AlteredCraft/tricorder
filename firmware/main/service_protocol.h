#pragma once
#include <cmath>
#include <cstdint>
#include "cJSON.h"

// One session with the Mac service, owned by the media task: hello -> ready, an
// optional voice note (recorded, transcribed, confirmed), then the caller's
// analysis_explain exchange. Wire format: planning/service.md.
class ServiceProtocol {
public:
    enum class State { Idle, Connecting, Ready, Asking, Transcribing, Confirming, Offline, Incomplete };
    static constexpr unsigned max_questions=5,max_question_frames=128000;
    ServiceProtocol(const char* boot, const char* session);
    bool ask(uint64_t now);
    // Voice note (ADR-0013), only at Ready. The audio is its own buffer; only its
    // identity is kept here. The host transcribes it; a heard transcript must be
    // confirmed (accepted or not) before anything else is sent.
    bool start_question();
    bool question_recorded(const cJSON* metadata,uint64_t now);
    cJSON* confirm_question(bool accepted);
    bool speech_available() const {return speech_;}
    bool speech_output() const {return voice_;} // the host can speak replies
    unsigned questions_left() const {return speech_?max_questions-questions_:0;}
    const char* question_id() const {return question_id_;}
    const char* transcript() const {return transcript_;}
    const char* transcript_status() const {return status_;} // heard, empty, failed or ""
    double speech_to_noise_db() const {return speech_to_noise_db_;}
    bool receive(const char* wire, uint64_t now);
    void tick(uint64_t now);
    void disconnect();
    void fail();
    bool terminal() const;
    State state() const {return state_;}
    const char* state_name() const;
    cJSON* envelope(const char* type) const;
    const char* boot() const {return boot_;}
    const char* session() const {return session_;}
    bool same_session(const cJSON* message) const;
    static cJSON* parse(const char* wire); // strict bounded JSON; caller owns
private:
    State state_=State::Idle;
    char boot_[97]{},session_[97]{};
    char question_id_[97]{},transcript_[513]{},status_[8]{};
    bool speech_=false,voice_=false;
    unsigned questions_=0;
    double speech_to_noise_db_=NAN;
    uint64_t deadline_=0;
};
