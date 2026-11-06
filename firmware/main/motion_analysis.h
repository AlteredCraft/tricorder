#pragma once
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdio>
// Motion session analysis (F-0005): what happened while the Motion screen sampled the
// accelerometer. Raw BMI270 counts in, g out. Not calibrated, and the sensor measures
// the device itself. Host-testable; no allocation.
namespace motion {
constexpr float sample_hz=100,counts_per_g=8192; // BMI270 at +/-4 g (imu_checked.cpp)
constexpr size_t second_samples=100,max_seconds=600,max_events=12;
// Movement: the spread (standard deviation) of the acceleration vector within one second.
// Unlike the magnitude alone, it also rises when the device turns.
constexpr float still_max_g=0.006f,hand_max_g=0.05f;
// An event is a run at least event_rise_g over the quiet level (the median change from
// gravity), merged across gaps shorter than event_gap_s.
constexpr float event_rise_g=0.1f,event_gap_s=0.2f;
constexpr float flat_max_deg=30,upright_min_deg=60;
// Vibration: 2 s windows where the device rested (its orientation moved less than
// rest_max_deg and nothing crossed the event threshold).
constexpr size_t vibration_window=200,max_vibration_windows=60;
constexpr float rest_max_deg=2,min_rest_s=4,min_vibration_hz=2,vibration_prominence=4,vibration_min_g=0.001f;
struct Sample {int16_t x,y,z;};
enum Steadiness {HeldStill,InHand,Moving};
enum Orientation {Flat,Tilted,Upright};
struct Event {float start_s,duration_s,peak_g;};
struct Second {float movement_g,tilt_deg;};
struct Analysis {
    unsigned samples;float duration_s;
    float gravity_g,quiet_g,threshold_g,peak_g,peak_at_s; // peak_g: largest change from gravity
    unsigned seconds;Second second[max_seconds];         // whole seconds, first max_seconds
    Steadiness steadiness;float typical_g,steadiest_g,steadiest_at_s,shakiest_g,shakiest_at_s;
    unsigned steadiness_s[3];                            // seconds held still, in hand, moving
    unsigned event_count;Event events[max_events];       // first max_events in time; event_count counts all
    float tilt_min_deg,tilt_max_deg;Orientation orientation;unsigned orientation_s[3];
    float rest_s;bool vibration;float vibration_hz,vibration_g;
};
struct Workspace {
    float cos[vibration_window],sin[vibration_window],hann[vibration_window],segment[vibration_window];
    float power[vibration_window/2];
};
inline float magnitude_g(const Sample& s) {
    return std::sqrt(float(s.x)*s.x+float(s.y)*s.y+float(s.z)*s.z)/counts_per_g;
}
// Degrees from lying flat (screen up or down), as home::tilt_degrees.
inline float tilt_deg(float x,float y,float z) {
    const float m=std::sqrt(x*x+y*y+z*z);
    return m>0?std::acos(std::min(1.0f,std::fabs(z)/m))*57.29578f:0;
}
inline float median(float* values,size_t n) {
    std::nth_element(values,values+n/2,values+n);return values[n/2];
}
inline void mean_vector(const Sample* s,size_t n,float* out) {
    double sum[3]{};
    for(size_t i=0;i<n;++i){sum[0]+=s[i].x;sum[1]+=s[i].y;sum[2]+=s[i].z;}
    for(int a=0;a<3;++a)out[a]=static_cast<float>(sum[a]/n);
}
inline float angle_deg(const float* a,const float* b) {
    const float dot=a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
    const float na=std::sqrt(a[0]*a[0]+a[1]*a[1]+a[2]*a[2]),nb=std::sqrt(b[0]*b[0]+b[1]*b[1]+b[2]*b[2]);
    if(na<=0 || nb<=0)return 180;
    return std::acos(std::clamp(dot/(na*nb),-1.0f,1.0f))*57.29578f;
}
inline Orientation orientation_of(float tilt) {return tilt<flat_max_deg?Flat:tilt<upright_min_deg?Tilted:Upright;}
inline Steadiness steadiness_of(float movement) {return movement<still_max_g?HeldStill:movement<hand_max_g?InHand:Moving;}

// scratch holds n floats. Needs at least two seconds of samples at sample_hz.
inline bool analyze(const Sample* s,size_t n,float* scratch,Workspace& w,Analysis& a) {
    if(n<2*second_samples)return false;
    a=Analysis{};a.samples=n;a.duration_s=n/sample_hz;
    for(size_t i=0;i<n;++i)scratch[i]=magnitude_g(s[i]);
    a.gravity_g=median(scratch,n);
    auto change=[&](size_t i){return std::fabs(magnitude_g(s[i])-a.gravity_g);};
    for(size_t i=0;i<n;++i) {
        scratch[i]=change(i);
        if(scratch[i]>a.peak_g){a.peak_g=scratch[i];a.peak_at_s=i/sample_hz;}
    }
    a.quiet_g=median(scratch,n);a.threshold_g=a.quiet_g+event_rise_g;
    const size_t gap=static_cast<size_t>(std::ceil(event_gap_s*sample_hz-1e-4f));
    for(size_t i=0;i<n;) {
        if(change(i)<a.threshold_g){++i;continue;}
        size_t last=i,j=i+1;
        for(;j<n && j<=last+gap;++j)if(change(j)>=a.threshold_g)last=j;
        if(a.event_count<max_events) {
            float peak=0;for(size_t k=i;k<=last;++k)peak=std::max(peak,change(k));
            a.events[a.event_count]={i/sample_hz,(last-i+1)/sample_hz,peak};
        }
        ++a.event_count;i=last+1;
    }
    const size_t seconds=n/second_samples;
    a.tilt_min_deg=180;a.steadiest_g=1e9f;
    for(size_t k=0;k<seconds;++k) {
        const Sample* p=s+k*second_samples;float mean[3];mean_vector(p,second_samples,mean);
        double spread=0;
        for(size_t i=0;i<second_samples;++i) {
            const float d[3]={p[i].x-mean[0],p[i].y-mean[1],p[i].z-mean[2]};spread+=d[0]*d[0]+d[1]*d[1]+d[2]*d[2];
        }
        const float movement=static_cast<float>(std::sqrt(spread/second_samples))/counts_per_g;
        const float tilt=tilt_deg(mean[0],mean[1],mean[2]);
        if(k<max_seconds){a.second[k]={movement,tilt};a.seconds=k+1;}
        scratch[k]=movement;++a.steadiness_s[steadiness_of(movement)];++a.orientation_s[orientation_of(tilt)];
        if(movement<a.steadiest_g){a.steadiest_g=movement;a.steadiest_at_s=k;}
        if(movement>a.shakiest_g){a.shakiest_g=movement;a.shakiest_at_s=k;}
        a.tilt_min_deg=std::min(a.tilt_min_deg,tilt);a.tilt_max_deg=std::max(a.tilt_max_deg,tilt);
    }
    a.typical_g=median(scratch,seconds);a.steadiness=steadiness_of(a.typical_g);
    a.orientation=static_cast<Orientation>(std::max_element(a.orientation_s,a.orientation_s+3)-a.orientation_s);

    // Vibration: the strongest frequency in the summed power of the three axes, averaged
    // over the resting windows, when it stands well above the median of the spectrum.
    constexpr size_t N=vibration_window,low_bin=static_cast<size_t>(min_vibration_hz*N/sample_hz),bins=N/2;
    auto rests=[&](size_t start) {
        float first[3],second[3];mean_vector(s+start,N/2,first);mean_vector(s+start+N/2,N/2,second);
        if(angle_deg(first,second)>rest_max_deg)return false;
        for(size_t i=start;i<start+N;++i)if(change(i)>=a.threshold_g)return false;
        return true;
    };
    for(size_t k=0;k<N;++k) {
        const float phase=6.2831853f*k/N;
        w.cos[k]=std::cos(phase);w.sin[k]=std::sin(phase);w.hann[k]=0.5f-0.5f*w.cos[k];
    }
    for(auto& p:w.power)p=0;
    unsigned resting=0,used=0;
    for(size_t start=0;start+N<=n;start+=N) {
        if(!rests(start))continue;
        ++resting;if(used==max_vibration_windows)continue;
        ++used;
        for(int axis=0;axis<3;++axis) {
            double mean=0;
            for(size_t i=0;i<N;++i)mean+=axis==0?s[start+i].x:axis==1?s[start+i].y:s[start+i].z;
            mean/=N;
            for(size_t i=0;i<N;++i) {
                const float v=axis==0?s[start+i].x:axis==1?s[start+i].y:s[start+i].z;
                w.segment[i]=static_cast<float>(v-mean)/counts_per_g*w.hann[i];
            }
            for(size_t b=low_bin;b<bins;++b) {
                float re=0,im=0;
                for(size_t i=0;i<N;++i){const size_t t=(b*i)%N;re+=w.segment[i]*w.cos[t];im+=w.segment[i]*w.sin[t];}
                // A sine of amplitude A gives |X| = A*N/4 under a Hann window.
                const float amplitude=4*std::sqrt(re*re+im*im)/N;w.power[b]+=amplitude*amplitude;
            }
        }
    }
    a.rest_s=resting*N/sample_hz;
    if(used && a.rest_s>=min_rest_s) {
        size_t best=low_bin;
        for(size_t b=low_bin;b<bins;++b){scratch[b-low_bin]=std::sqrt(w.power[b]/used);if(w.power[b]>w.power[best])best=b;}
        const float peak=std::sqrt(w.power[best]/used),typical=median(scratch,bins-low_bin);
        if(peak>=vibration_min_g && peak>=vibration_prominence*typical) {
            a.vibration=true;a.vibration_hz=best*sample_hz/N;a.vibration_g=peak;
        }
    }
    return true;
}
inline const char* steadiness_name(Steadiness s) {return s==HeldStill?"held still":s==InHand?"in hand":"moving";}
inline const char* orientation_name(Orientation o) {return o==Flat?"flat":o==Tilted?"tilted":"upright";}
// Below 0.1 g in milli-g, otherwise g.
inline void g_text(float g,char* out,size_t size) {
    if(std::fabs(g)<0.1f)snprintf(out,size,"%.0f mg",g*1000);
    else snprintf(out,size,"%.2f g",g);
}
}
