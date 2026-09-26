#pragma once
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdio>
// Sound session analysis (F-0002): what happened while the Sound screen listened,
// from display-only frames of level and 48 band levels. Relative dB only: the
// microphone path is not calibrated. Host-testable; no allocation.
namespace sound {
constexpr size_t analysis_bands=48; // spectrum_band_count
constexpr float event_rise_db=10,event_min_s=0.3f,event_gap_s=0.3f,tone_rise_db=6,silent_band_db=-100;
constexpr size_t max_events=12,max_tones=4;
struct Frame {float level_db;float band_db[analysis_bands];};
struct Event {float start_s,duration_s,peak_over_db,band_hz,band_rise_db;};
struct Tone {float hz,above_db;};
struct Analysis {
    unsigned frames;float duration_s;
    float background_db,loud_db,average_db,max_db,max_at_s,threshold_db;
    unsigned event_count;Event events[max_events]; // first max_events in time; event_count counts all
    unsigned tone_count;Tone tones[max_tones];       // strongest first
    float strongest_background_hz;
};
inline float power(float db){return std::pow(10.0f,db/10.0f);}
inline float decibels(double p){return p>0?10.0f*static_cast<float>(std::log10(p)):-200.0f;}
// q in [0,1]; reorders scratch.
inline float percentile(float* values,size_t n,float q) {
    const size_t k=std::min(n-1,static_cast<size_t>(q*(n-1)+0.5f));
    std::nth_element(values,values+k,values+n);return values[k];
}
// Background is the level exceeded 90% of the time (L90); loud, 10% (L10); average,
// the energy mean (Leq). An event is a run of frames at least event_rise_db above
// the background, merged across gaps shorter than event_gap_s, lasting at least
// event_min_s; its band is the one that rose most over that band's median. A steady
// tone is a band whose median stands tone_rise_db above its two neighbours on each side.
inline bool analyze(const Frame* frames,size_t n,float period_s,const float* band_hz,float* scratch,Analysis& a) {
    if(n<10 || period_s<=0)return false;
    a=Analysis{};a.frames=n;a.duration_s=n*period_s;
    double energy=0;a.max_db=frames[0].level_db;
    for(size_t i=0;i<n;++i) {
        scratch[i]=frames[i].level_db;energy+=power(frames[i].level_db);
        if(frames[i].level_db>a.max_db){a.max_db=frames[i].level_db;a.max_at_s=i*period_s;}
    }
    a.average_db=decibels(energy/n);
    a.background_db=percentile(scratch,n,0.1f);
    a.loud_db=percentile(scratch,n,0.9f);
    a.threshold_db=a.background_db+event_rise_db;
    float median[analysis_bands];
    for(size_t b=0;b<analysis_bands;++b) {
        for(size_t i=0;i<n;++i)scratch[i]=frames[i].band_db[b];
        median[b]=percentile(scratch,n,0.5f);
    }
    a.strongest_background_hz=band_hz[std::max_element(median,median+analysis_bands)-median];
    const size_t gap=static_cast<size_t>(std::ceil(event_gap_s/period_s-1e-4f));
    const size_t shortest=static_cast<size_t>(std::ceil(event_min_s/period_s-1e-4f));
    for(size_t i=0;i<n;) {
        if(frames[i].level_db<a.threshold_db){++i;continue;}
        size_t last=i,j=i+1;
        for(;j<n && j<=last+gap;++j)if(frames[j].level_db>=a.threshold_db)last=j;
        const size_t first=i,count=last-first+1;i=last+1;
        if(count<shortest)continue;
        if(a.event_count<max_events) {
            Event& e=a.events[a.event_count];
            e.start_s=first*period_s;e.duration_s=count*period_s;
            float peak=frames[first].level_db;
            for(size_t k=first;k<=last;++k)peak=std::max(peak,frames[k].level_db);
            e.peak_over_db=peak-a.background_db;e.band_rise_db=-1000;
            for(size_t b=0;b<analysis_bands;++b) {
                double p=0;for(size_t k=first;k<=last;++k)p+=power(frames[k].band_db[b]);
                const float rise=decibels(p/count)-median[b];
                if(rise>e.band_rise_db){e.band_rise_db=rise;e.band_hz=band_hz[b];}
            }
        }
        ++a.event_count;
    }
    for(size_t b=2;b+2<analysis_bands;++b) {
        if(median[b]<=silent_band_db)continue;
        const float neighbours=(median[b-2]+median[b-1]+median[b+1]+median[b+2])/4;
        const float above=median[b]-neighbours;
        if(above<tone_rise_db)continue;
        // Keep the strongest max_tones, strongest first.
        size_t at=a.tone_count<max_tones?a.tone_count:max_tones;
        if(at==max_tones && above<=a.tones[max_tones-1].above_db)continue;
        if(at==max_tones)--at;
        while(at>0 && a.tones[at-1].above_db<above){a.tones[at]=a.tones[at-1];--at;}
        a.tones[at]={band_hz[b],above};
        if(a.tone_count<max_tones)++a.tone_count;
    }
    return true;
}
// The loudest value in each of `points` equal buckets.
inline void bucket_max(const float* values,size_t n,float* out,size_t points) {
    for(size_t p=0;p<points;++p) {
        const size_t begin=p*n/points,end=std::max(begin+1,(p+1)*n/points);
        out[p]=*std::max_element(values+begin,values+std::min(end,n));
    }
}
inline void clock_text(float seconds,char* out,size_t size) {
    const int s=static_cast<int>(seconds);snprintf(out,size,"%d:%02d",s/60,s%60);
}
inline void hz_text(float hz,char* out,size_t size) {
    if(hz<1000)snprintf(out,size,"%.0f Hz",hz);
    else if(hz<10000)snprintf(out,size,"%.1f kHz",hz/1000);
    else snprintf(out,size,"%.0f kHz",hz/1000);
}
}
