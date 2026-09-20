#pragma once
#include <cstdint>
#include <cstddef>
struct CameraIngressSnapshot {uint64_t requests=0,missing_buffers=0,finished=0,bytes=0,untracked_buffers=0;size_t expected_bytes=0;};
struct CameraFrameEvidence {uint64_t sequence=0;int64_t finished_us=0;size_t bytes=0;};
// Query only while the dequeued buffer is still owned by the caller.
bool camera_frame_evidence(const void* buffer,CameraFrameEvidence& evidence);
// Set the configured full-frame byte size while the camera is stopped.
void configure_camera_ingress(size_t expected_bytes);
CameraIngressSnapshot camera_ingress_snapshot();
