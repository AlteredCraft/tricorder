#pragma once
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdio>
// Power session analysis (F-0007): what the battery branch did while the Power screen
// sampled the INA226. Volts and amps in; the draw, its changes and the energy used out.
// Positive current flows out of the battery, negative into it (G-0001.05 C1). On USB the
// device runs from USB, so the branch carries no current. Host-testable; no allocation.
namespace power {
constexpr float sample_hz=10;
constexpr size_t second_samples=10,max_seconds=600,max_steps=12,max_marks=12;
constexpr float no_current_a=0.02f;        // |current| below this: no battery current
constexpr float step_a=0.03f;              // a change in the per-second draw this large...
constexpr size_t step_hold_s=2;            // ...that holds this long is a step
constexpr float full_v=8.4f,empty_v=6.6f;  // two-cell lithium pack, resting
struct Sample {float v,a;};
struct Mark {size_t sample;uint8_t brightness;};  // a backlight change while sampling
enum Source {Battery,Charging,NoCurrent};
struct Step {float at_s,from_a,to_a;};
struct Second {float v,a;};
struct ScreenChange {float at_s;uint8_t brightness;float before_a,after_a;};
struct Analysis {
    unsigned samples;float duration_s;
    float v_start,v_end,v_min,v_max;
    unsigned battery_s,charging_s,no_current_s;Source source;  // whole seconds, by their mean current
    float draw_typical_a,draw_min_a,draw_max_a,draw_max_at_s;  // on battery; 0 when never on battery
    float power_typical_w,power_max_w;
    float charge_typical_a;                                    // while charging; 0 when never
    float used_mah,used_mwh,charged_mah;
    float battery_pct;                                         // rough, from the volts; -1 unless on battery
    unsigned seconds;Second second[max_seconds];               // every whole second (max_seconds covers 10 min)
    unsigned step_count;Step steps[max_steps];                 // first max_steps in time; step_count counts all
    unsigned change_count;ScreenChange changes[max_marks];     // marks with 2 s measured before and after
};
inline float median(float* values,size_t n) {
    if(!n)return 0;
    std::nth_element(values,values+n/2,values+n);return values[n/2];
}
inline Source source_of(float a) {return a>=no_current_a?Battery:a<=-no_current_a?Charging:NoCurrent;}
inline float battery_percent(float v) {return std::clamp((v-empty_v)/(full_v-empty_v)*100,0.0f,100.0f);}
inline float mean_a(const Sample* s,size_t begin,size_t end) {
    double sum=0;for(size_t i=begin;i<end;++i)sum+=s[i].a;
    return end>begin?static_cast<float>(sum/(end-begin)):0;
}

// scratch holds n floats. Needs at least two seconds of samples at sample_hz.
inline bool analyze(const Sample* s,size_t n,const Mark* marks,size_t mark_count,float* scratch,Analysis& a) {
    if(n<2*second_samples)return false;
    n=std::min(n,max_seconds*second_samples);
    a=Analysis{};a.samples=n;a.duration_s=n/sample_hz;
    a.v_start=s[0].v;a.v_end=s[n-1].v;a.v_min=1e9f;a.v_max=-1e9f;a.battery_pct=-1;
    const float dt_h=1/sample_hz/3600;
    double used_mah=0,used_mwh=0,charged_mah=0;
    for(size_t i=0;i<n;++i) {
        a.v_min=std::min(a.v_min,s[i].v);a.v_max=std::max(a.v_max,s[i].v);
        if(s[i].a>0) {
            used_mah+=s[i].a*dt_h*1000;used_mwh+=s[i].a*s[i].v*dt_h*1000;
            a.power_max_w=std::max(a.power_max_w,s[i].a*s[i].v);
            if(s[i].a>a.draw_max_a){a.draw_max_a=s[i].a;a.draw_max_at_s=i/sample_hz;}
        } else charged_mah-=s[i].a*dt_h*1000;
    }
    a.used_mah=static_cast<float>(used_mah);a.used_mwh=static_cast<float>(used_mwh);a.charged_mah=static_cast<float>(charged_mah);
    a.seconds=n/second_samples;
    for(size_t k=0;k<a.seconds;++k) {
        double v=0,c=0;
        for(size_t i=k*second_samples;i<(k+1)*second_samples;++i){v+=s[i].v;c+=s[i].a;}
        a.second[k]={static_cast<float>(v/second_samples),static_cast<float>(c/second_samples)};
        const Source src=source_of(a.second[k].a);
        if(src==Battery)++a.battery_s;else if(src==Charging)++a.charging_s;else ++a.no_current_s;
    }
    const unsigned counts[3]={a.battery_s,a.charging_s,a.no_current_s};
    a.source=static_cast<Source>(std::max_element(counts,counts+3)-counts);
    // Typical draw and power: medians over the seconds on battery.
    size_t m=0;a.draw_min_a=1e9f;
    for(size_t k=0;k<a.seconds;++k)if(source_of(a.second[k].a)==Battery){scratch[m++]=a.second[k].a;a.draw_min_a=std::min(a.draw_min_a,a.second[k].a);}
    a.draw_typical_a=median(scratch,m);
    if(!m)a.draw_min_a=0;
    m=0;
    for(size_t k=0;k<a.seconds;++k)if(source_of(a.second[k].a)==Battery)scratch[m++]=a.second[k].a*a.second[k].v;
    a.power_typical_w=median(scratch,m);
    m=0;
    for(size_t k=0;k<a.seconds;++k)if(source_of(a.second[k].a)==Charging)scratch[m++]=-a.second[k].a;
    a.charge_typical_a=median(scratch,m);
    if(a.source==Battery)a.battery_pct=battery_percent(a.v_max); // the highest volts are nearest the resting value
    // Steps: the per-second draw settles at a new level at least step_a from the last one.
    float level=a.second[0].a;
    for(size_t k=1;k+step_hold_s<=a.seconds;) {
        float sum=0;
        for(size_t j=k;j<k+step_hold_s;++j)sum+=a.second[j].a;
        const float next=sum/step_hold_s;bool steady=true;
        for(size_t j=k;j<k+step_hold_s;++j)if(std::fabs(a.second[j].a-next)>step_a/2)steady=false;
        if(steady && std::fabs(next-level)>=step_a) {
            if(a.step_count<max_steps)a.steps[a.step_count]={static_cast<float>(k),level,next};
            ++a.step_count;level=next;k+=step_hold_s;
        } else ++k;
    }
    // Screen changes: the mean draw 2 s before the mark against 2 s after a half-second settle.
    constexpr size_t before=2*second_samples,settle=second_samples/2,after=2*second_samples;
    for(size_t i=0;i<mark_count && a.change_count<max_marks;++i) {
        const size_t at=marks[i].sample;
        if(at<before || at+settle+after>n)continue;
        a.changes[a.change_count++]={at/sample_hz,marks[i].brightness,mean_a(s,at-before,at),mean_a(s,at+settle,at+settle+after)};
    }
    return true;
}
inline const char* source_name(Source s) {return s==Battery?"battery":s==Charging?"charging":"no battery current";}
// Below 1 A in mA, otherwise A.
inline void a_text(float a,char* out,size_t size) {
    if(std::fabs(a)<1)snprintf(out,size,"%.0f mA",a*1000);
    else snprintf(out,size,"%.2f A",a);
}
// Below 1 W in mW, otherwise W.
inline void w_text(float w,char* out,size_t size) {
    if(std::fabs(w)<1)snprintf(out,size,"%.0f mW",w*1000);
    else snprintf(out,size,"%.1f W",w);
}
}
