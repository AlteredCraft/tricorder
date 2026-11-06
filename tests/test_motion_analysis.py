import shutil
import subprocess
import tempfile
from pathlib import Path
import unittest


class MotionAnalysisTests(unittest.TestCase):
    def test_steadiness_events_tilt_vibration_and_formatting(self):
        compiler = shutil.which('clang++') or shutil.which('g++')
        self.assertIsNotNone(compiler)
        source = r'''
#include "motion_analysis.h"
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <vector>
using namespace motion;
bool near(float a,float b,float tolerance){return std::fabs(a-b)<=tolerance;}
uint32_t seed=1;
int16_t noise(){seed=seed*1664525u+1013904223u;return static_cast<int16_t>(static_cast<int>(seed>>28)-8);}
int16_t counts(double g){return static_cast<int16_t>(std::lround(g*counts_per_g));}
struct Run {std::vector<Sample> s;std::vector<float> scratch;Workspace w;Analysis a;
    bool analyze(){scratch.resize(s.size());return motion::analyze(s.data(),s.size(),scratch.data(),w,a);}};
int main() {
    const double pi=3.14159265358979;
    // 0-10 s flat and still with a 4 mg, 25 Hz vibration and a 0.5 g tap at 5.00 s;
    // 10-20 s upright in hand, turning 3 degrees a second; 20-25 s flat, shaken 0.8 g at 4 Hz.
    Run r;
    for(size_t i=0;i<2500;++i) {
        const double t=i/100.0;Sample s{noise(),noise(),noise()};
        if(t<10) {
            s.z+=counts(1+0.004*std::sin(2*pi*25*t));
            if(i>=500 && i<503)s.z+=counts(0.5);
        } else if(t<20) {
            const double turn=3*(t-10)*pi/180;s.x+=counts(std::sin(turn));s.y+=counts(std::cos(turn));
        } else s.z+=counts(1+0.8*std::sin(2*pi*4*(t-20)));
        r.s.push_back(s);
    }
    assert(r.analyze());
    const Analysis& a=r.a;
    assert(a.samples==2500 && near(a.duration_s,25,0.01f) && a.seconds==25);
    assert(near(a.gravity_g,1,0.01f) && a.quiet_g<0.01f && near(a.threshold_g,a.quiet_g+0.1f,1e-4f));
    assert(near(a.peak_g,0.8f,0.02f) && a.peak_at_s>=20);
    // The tap makes second 5 a moving second.
    assert(a.steadiness_s[HeldStill]==9 && a.steadiness_s[InHand]==10 && a.steadiness_s[Moving]==6);
    assert(a.steadiness==InHand && a.typical_g>still_max_g && a.typical_g<hand_max_g);
    assert(a.steadiest_at_s<10 && a.steadiest_g<still_max_g);
    assert(a.shakiest_at_s>=20 && near(a.shakiest_g,0.57f,0.03f));
    assert(a.event_count==2);
    assert(near(a.events[0].start_s,5,0.001f) && near(a.events[0].duration_s,0.03f,0.001f) && near(a.events[0].peak_g,0.5f,0.02f));
    assert(near(a.events[1].start_s,20,0.05f) && near(a.events[1].duration_s,5,0.1f) && near(a.events[1].peak_g,0.8f,0.02f));
    assert(a.tilt_min_deg<1 && a.tilt_max_deg>89);
    assert(a.orientation==Flat && a.orientation_s[Flat]==15 && a.orientation_s[Upright]==10 && a.orientation_s[Tilted]==0);
    assert(near(a.second[15].tilt_deg,90,0.5f) && a.second[3].tilt_deg<1);
    // Rests: 0-10 s in 2 s windows, less the one with the tap. The turning hand and the shake don't count.
    assert(near(a.rest_s,8,0.01f));
    assert(a.vibration && near(a.vibration_hz,25,0.01f) && near(a.vibration_g,0.004f,0.0005f));

    // Still with noise only: rested, nothing stands out. Spikes 0.15 s apart merge; 0.5 s apart don't.
    Run q;
    for(size_t i=0;i<1000;++i) {
        Sample s{noise(),noise(),static_cast<int16_t>(counts(1)+noise())};
        if(i==100 || i==115 || i==300 || i==350)s.z+=counts(0.3);
        q.s.push_back(s);
    }
    assert(q.analyze());
    assert(q.a.event_count==3 && near(q.a.events[0].duration_s,0.16f,0.001f) && near(q.a.events[1].start_s,3,0.001f));
    assert(q.a.steadiness==HeldStill && q.a.orientation==Flat);
    assert(near(q.a.rest_s,6,0.01f) && !q.a.vibration);

    // Too short to analyze.
    Run tiny;tiny.s.assign(150,Sample{0,0,8192});
    assert(!tiny.analyze());

    char text[32];
    g_text(0.0042f,text,sizeof(text));assert(!strcmp(text,"4 mg"));
    g_text(0.456f,text,sizeof(text));assert(!strcmp(text,"0.46 g"));
    assert(!strcmp(steadiness_name(InHand),"in hand") && !strcmp(orientation_name(Upright),"upright"));
}
'''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'test.cpp').write_text(source)
            subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
                            '-I', 'firmware/main', str(root/'test.cpp'), '-o', str(root/'test')], check=True)
            subprocess.run([str(root/'test')], check=True)


if __name__ == '__main__':
    unittest.main()
