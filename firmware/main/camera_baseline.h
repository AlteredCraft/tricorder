#pragma once
#include "camera_buffers.h"
#include "linux/videodev2.h"
#include <cstddef>
#include <cstdint>
// Called by the sole video owner after STREAMON. Stops the stream, retaining
// the final dequeued buffer for the caller's isolated image export.
bool run_camera_baseline(int fd,const v4l2_format& format,uint8_t* const* buffers,const size_t* lengths,
                         const char* boot_id,v4l2_buffer& last,int64_t& last_dequeue_us);
