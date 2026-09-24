#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>

// Hand-held stillness from BMI270 samples as configured by imu_checked
// (gyro ±1000 dps, accel ±4 g). Display and operator guidance only; the
// thresholds are provisional and not a measurement claim.
struct SteadinessReading {
    enum State {Unknown,Steady,Moving} state=Unknown;
    float peak_dps=0,accel_span_g=0;
    unsigned samples=0;
};

class Steadiness {
public:
    static constexpr float gyro_lsb_per_dps=32.768f,accel_lsb_per_g=8192;
    static constexpr uint32_t window_ms=500,stale_ms=200;
    static constexpr unsigned min_samples=5;
    static constexpr float steady_dps=4,steady_span_g=0.05f;

    void add(uint32_t t_ms,const int16_t gyro[3],const int16_t accel[3]) {
        auto magnitude=[](const int16_t v[3],float scale) {
            return std::sqrt(float(v[0])*v[0]+float(v[1])*v[1]+float(v[2])*v[2])/scale;
        };
        ring_[next_]={t_ms,magnitude(gyro,gyro_lsb_per_dps),magnitude(accel,accel_lsb_per_g)};
        next_=(next_+1)%capacity;count_=std::min(count_+1,capacity);
    }
    // A failed read leaves no trustworthy window.
    void fail(uint32_t) {count_=0;}
    SteadinessReading read(uint32_t now_ms) const {
        SteadinessReading r;
        float low=0,high=0;uint32_t latest=0;
        for (unsigned i=0;i<count_;++i) {
            const auto& s=ring_[i];
            if (s.t>now_ms || now_ms-s.t>=window_ms) continue;
            if (!r.samples++) {low=high=s.g;latest=s.t;}
            r.peak_dps=std::max(r.peak_dps,s.dps);
            low=std::min(low,s.g);high=std::max(high,s.g);latest=std::max(latest,s.t);
        }
        r.accel_span_g=high-low;
        if (r.samples<min_samples || now_ms-latest>stale_ms) r.state=SteadinessReading::Unknown;
        else r.state=r.peak_dps<=steady_dps && r.accel_span_g<=steady_span_g ?
            SteadinessReading::Steady:SteadinessReading::Moving;
        return r;
    }
private:
    static constexpr unsigned capacity=32;
    struct Sample {uint32_t t=0;float dps=0,g=0;};
    Sample ring_[capacity];
    unsigned next_=0,count_=0;
};
