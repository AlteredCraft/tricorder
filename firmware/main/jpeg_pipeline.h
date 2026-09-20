#pragma once
#include <cstddef>
#include <cstdint>
#include "camera_ingress.h"
class JpegPipeline {
public:
    JpegPipeline(unsigned width,unsigned height);
    ~JpegPipeline();
    bool ready() const;
    void begin(int64_t epoch);
    bool submit(const uint8_t* source,size_t bytes,const CameraFrameEvidence& frame,int64_t dequeued);
    void dispatch();
    void wait_idle();
    bool export_results(const char* boot_id);
private:
    struct State;
    State* state_=nullptr;
    JpegPipeline(const JpegPipeline&)=delete;
    JpegPipeline& operator=(const JpegPipeline&)=delete;
};
