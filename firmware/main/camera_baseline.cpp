#include "camera_baseline.h"
#include "camera_ingress.h"
#include "jpeg_pipeline.h"
#include "diagnostic_events.h"
#include "workload_metrics.h"
#include "media.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <sys/ioctl.h>
#include <cstdlib>
#include <cstdio>

struct CameraMemory {size_t internal,external,largest,stack,task_sram,largest_task_sram;};
struct CameraRunStorage {
    uint64_t* rows=static_cast<uint64_t*>(heap_caps_malloc(4096*5*sizeof(uint64_t),MALLOC_CAP_SPIRAM));
    CameraMemory* memory=static_cast<CameraMemory*>(calloc(137,sizeof(CameraMemory)));
    cJSON* cpu_before=nullptr; cJSON* cpu_after=nullptr;
    ~CameraRunStorage() {free(rows);free(memory);cJSON_Delete(cpu_before);cJSON_Delete(cpu_after);}
};

bool run_camera_baseline(int fd,const v4l2_format& format,uint8_t* const* buffers,const size_t* lengths,
                         const char* boot_id,v4l2_buffer& last,int64_t& last_dequeue_us) {
    CameraRunStorage saved;
    JpegPipeline jpeg(format.fmt.pix.width,format.fmt.pix.height);
    diagnostic_check("jpeg_initialize",jpeg.ready() ? "pass":"fail","Owned source/output/pool, bounded codec and JPEG worker initialization.");
    bool ok=saved.rows && saved.memory && jpeg.ready();
    auto dequeue=[&](v4l2_buffer& buffer) {
        buffer={};buffer.type=V4L2_BUF_TYPE_VIDEO_CAPTURE;buffer.memory=V4L2_MEMORY_MMAP;
        return ioctl(fd,VIDIOC_DQBUF,&buffer)==0 && buffer.index<camera_capture_buffer_count && buffer.bytesused && buffer.bytesused<=lengths[buffer.index];
    };
    for (unsigned i=0;ok && i<10;++i) {
        v4l2_buffer buffer;
        ok=dequeue(buffer) && ioctl(fd,VIDIOC_QBUF,&buffer)==0;
    }
    // Warm-up occurs before the measured epoch, including initial exposure settling.
    saved.cpu_before=workload_cpu_snapshot();
    auto before=camera_ingress_snapshot();
    int64_t started=esp_timer_get_time();
    jpeg.begin(started);
    int64_t next_jpeg=2000000;
    bool jpeg_pending=false;
    bool final_jpeg=false;
    CameraFrameEvidence final_frame;
    size_t count=0;
    uint64_t previous_sequence=before.finished,order_errors=0;
    while (ok && count<4096) {
        v4l2_buffer buffer;
        if (!dequeue(buffer)) {ok=false;break;}
        const int64_t dequeued=esp_timer_get_time();
        CameraFrameEvidence frame;
        if (!camera_frame_evidence(buffers[buffer.index],frame) || frame.bytes!=buffer.bytesused) {ok=false;break;}
        if (frame.sequence!=previous_sequence+1) ++order_errors;
        previous_sequence=frame.sequence;
        auto* row=saved.rows+count*5;
        row[0]=frame.sequence;row[1]=frame.finished_us-started;row[2]=dequeued-started;row[4]=buffer.bytesused;
        ++count;last=buffer;last_dequeue_us=dequeued;
        bool done=dequeued-started>=60000000;
        if (done) {
            // Stop acquisition promptly at the epoch boundary. Hash the final
            // retained source only after STREAMOFF, so its hash/copy work
            // cannot leave already-completed frames queued before the stop.
            final_jpeg=dequeued-started>=next_jpeg;final_frame=frame;
        } else if (dequeued-started>=next_jpeg) {
            jpeg_pending=jpeg.submit(buffers[buffer.index],buffer.bytesused,frame,dequeued);
            next_jpeg+=2000000;
        }
        // Keep the final image owned until STREAMOFF; no writer can reuse it.
        if (!done && ioctl(fd,VIDIOC_QBUF,&buffer)) {ok=false;break;}
        row[3]=esp_timer_get_time()-started;
        if (!done && jpeg_pending) {jpeg.dispatch();jpeg_pending=false;}
        if (count%30==0) {
            auto& m=saved.memory[count/30-1];
            m.internal=heap_caps_get_free_size(MALLOC_CAP_INTERNAL);m.external=heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
            m.largest=heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM);m.stack=uxTaskGetStackHighWaterMark(nullptr);
            constexpr auto task_caps=MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT|MALLOC_CAP_SIMD;
            m.task_sram=heap_caps_get_free_size(task_caps);m.largest_task_sram=heap_caps_get_largest_free_block(task_caps);
        }
        if (done) break;
    }
    int type=V4L2_BUF_TYPE_VIDEO_CAPTURE;
    const auto stop_request=camera_ingress_snapshot();
    bool stopped=ioctl(fd,VIDIOC_STREAMOFF,&type)==0;
    const int64_t ended=esp_timer_get_time();
    if (stopped && final_jpeg)
        jpeg_pending=jpeg.submit(buffers[last.index],last.bytesused,final_frame,last_dequeue_us);
    if (jpeg_pending) jpeg.dispatch();
    if (count) saved.rows[(count-1)*5+3]=ended-started;
    auto after=camera_ingress_snapshot();
    jpeg.wait_idle();saved.cpu_after=workload_cpu_snapshot();
    const uint64_t completed=after.finished-before.finished;
    ok=ok && stopped && count && ended-started>=60000000 && count<4096 && completed>=count && completed-count<=2
        && after.missing_buffers==before.missing_buffers && after.untracked_buffers==before.untracked_buffers;
    ok=ok && after.reused_completions==before.reused_completions && !order_errors;
    auto* meta=diagnostic_event("capture_start");
    cJSON_AddStringToObject(meta,"format","camera_baseline_u64le");
    cJSON_AddStringToObject(meta,"workload","camera plus JPEG every two seconds");
    cJSON_AddStringToObject(meta,"layout","completion_sequence,completed_us,dequeued_us,released_us,bytes; relative epoch times; final buffer released by STREAMOFF");
    cJSON_AddNumberToObject(meta,"rows",count);cJSON_AddNumberToObject(meta,"columns",5);
    cJSON_AddNumberToObject(meta,"width",format.fmt.pix.width);cJSON_AddNumberToObject(meta,"height",format.fmt.pix.height);
    cJSON_AddNumberToObject(meta,"frame_bytes",before.expected_bytes);
    cJSON_AddNumberToObject(meta,"capture_buffer_count",camera_capture_buffer_count);
    cJSON_AddNumberToObject(meta,"duration_us",ended-started);cJSON_AddNumberToObject(meta,"acquisition_start_us",started);
    cJSON_AddNumberToObject(meta,"completed_before",before.finished);cJSON_AddNumberToObject(meta,"completed_after",after.finished);
    cJSON_AddNumberToObject(meta,"missing_buffers",after.missing_buffers-before.missing_buffers);
    cJSON_AddNumberToObject(meta,"untracked_buffers",after.untracked_buffers-before.untracked_buffers);
    cJSON_AddNumberToObject(meta,"reused_completions",after.reused_completions-before.reused_completions);
    cJSON_AddNumberToObject(meta,"delivery_order_errors",order_errors);
    cJSON_AddNumberToObject(meta,"completed_at_stop_request",stop_request.finished);
    cJSON_AddNumberToObject(meta,"completed_bytes",after.bytes-before.bytes);
    cJSON_AddNumberToObject(meta,"buffer_requests",after.requests-before.requests);
    cJSON_AddNumberToObject(meta,"discarded_completed_at_stop",after.finished-stop_request.finished);
    auto* samples=cJSON_AddArrayToObject(meta,"memory_samples");
    for (size_t i=0;saved.memory && i<count/30;++i) {
        const auto& m=saved.memory[i];auto* item=cJSON_CreateObject();
        cJSON_AddNumberToObject(item,"frame_index",(i+1)*30);
        cJSON_AddNumberToObject(item,"free_internal",m.internal);cJSON_AddNumberToObject(item,"free_psram",m.external);
        cJSON_AddNumberToObject(item,"largest_psram",m.largest);cJSON_AddNumberToObject(item,"stack_margin_bytes",m.stack);
        cJSON_AddNumberToObject(item,"free_task_sram",m.task_sram);cJSON_AddNumberToObject(item,"largest_task_sram",m.largest_task_sram);
        cJSON_AddItemToArray(samples,item);
    }
    if (saved.cpu_before) {cJSON_AddItemToObject(meta,"cpu_before",saved.cpu_before);saved.cpu_before=nullptr;}
    if (saved.cpu_after) {cJSON_AddItemToObject(meta,"cpu_after",saved.cpu_after);saved.cpu_after=nullptr;}
    if (count) {
        char id[80];snprintf(id,sizeof(id),"%s-camera-baseline",boot_id);
        ok=export_diagnostic_capture(id,reinterpret_cast<const uint8_t*>(saved.rows),count*40,meta) && ok;
    } else cJSON_Delete(meta);
    diagnostic_check("camera_baseline",ok ? "pass":"fail","60-second camera completion/backup-buffer accounting; independent host timing check required.");
    jpeg.export_results(boot_id);
    return stopped && count && last.bytesused;
}
