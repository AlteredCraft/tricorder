#include "camera_ingress.h"
#include "esp_video.h"

extern "C" esp_video_buffer_element* __real_esp_video_recv_element(esp_video*,uint32_t,uint32_t);
extern "C" esp_video_buffer_element* __wrap_esp_video_recv_element(esp_video* video,uint32_t type,uint32_t ticks) {
    const uint32_t limit=pdMS_TO_TICKS(2000);
    ticks=ticks<limit ? ticks:limit;
    // Only the registered CSI owner gets FIFO capture delivery. Other video
    // devices retain the original path, including M2M trigger semantics.
    if (!camera_owns_video(video) || type!=V4L2_BUF_TYPE_VIDEO_CAPTURE)
        return __real_esp_video_recv_element(video,type,ticks);
    auto* stream=esp_video_get_stream(video,V4L2_BUF_TYPE_VIDEO_CAPTURE);
    if (!stream || xSemaphoreTake(stream->ready_sem,ticks)!=pdTRUE) return nullptr;
    // The pinned esp_video producer inserts at the head. Remove the tail
    // under its existing lock, without altering callbacks or semaphore counts.
    portENTER_CRITICAL_SAFE(&video->stream_lock);
    auto* oldest=SLIST_FIRST(&stream->done_list);
    if (oldest) {
        while (SLIST_NEXT(oldest,node)) oldest=SLIST_NEXT(oldest,node);
        SLIST_REMOVE(&stream->done_list,oldest,esp_video_buffer_element,node);
        ELEMENT_SET_FREE(oldest);
    }
    portEXIT_CRITICAL_SAFE(&video->stream_lock);
    return oldest;
}
