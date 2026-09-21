#pragma once
#include "camera_ingress.h"
#include <cstddef>
#include <cstdint>

class CameraPreview {
public:
    CameraPreview(unsigned width,unsigned height);
    ~CameraPreview();
    bool ready() const;
    void begin(int64_t epoch);
    bool offer(const uint8_t* source,size_t bytes,const CameraFrameEvidence& frame,int64_t dequeued);
    void finish();
    bool export_results(const char* boot_id,size_t camera_frames);
    CameraPreview(const CameraPreview&)=delete;
    CameraPreview& operator=(const CameraPreview&)=delete;
private:
    struct State;State* state_=nullptr;
};
