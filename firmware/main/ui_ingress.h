#pragma once
#include <cstdint>
#include <cstddef>

struct UiSubmissionRow {
    int64_t render,generation,changed_us,submitted_us,returned_us,x1,y1,x2,y2,result,last;
};
static_assert(sizeof(UiSubmissionRow)==11*sizeof(int64_t));
// Called only under the BSP display lock, including the LVGL callbacks.
class UiIngress {
public:
    UiIngress(UiSubmissionRow* rows,size_t capacity,int64_t epoch):rows_(rows),capacity_(capacity),epoch_(epoch) {}
    void animation(uint64_t generation,int64_t changed) {generation_=generation;changed_=changed;}
    void render() {++renders_;render_generation_=generation_;render_changed_=changed_;}
    void flush(bool last) {last_=last;}
    void submitted(int64_t start,int64_t end,int x1,int y1,int x2,int y2,int result) {
        ++submissions_;
        if (count_==capacity_) {++overflow_;return;}
        rows_[count_++]={int64_t(renders_),int64_t(render_generation_),render_changed_-epoch_,start-epoch_,end-epoch_,
                         x1,y1,x2,y2,result,last_};
    }
    size_t count() const {return count_;}
    uint64_t submissions() const {return submissions_;}
    uint64_t overflow() const {return overflow_;}
    uint64_t renders() const {return renders_;}
private:
    UiSubmissionRow* rows_;size_t capacity_,count_=0;int64_t epoch_,changed_=0,render_changed_=0;
    uint64_t generation_=0,render_generation_=0,renders_=0,submissions_=0,overflow_=0;
    bool last_=false;
};
void ui_observe(UiIngress* log);
void run_ui_baseline(const char* boot_id);
