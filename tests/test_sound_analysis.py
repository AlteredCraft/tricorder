import shutil
import subprocess
import tempfile
from pathlib import Path
import unittest


class SoundAnalysisTests(unittest.TestCase):
    def test_background_events_tones_and_formatting(self):
        compiler = shutil.which('clang++') or shutil.which('g++')
        self.assertIsNotNone(compiler)
        source = r'''
#include "sound_analysis.h"
#include <cassert>
#include <cmath>
#include <cstring>
#include <vector>
using namespace sound;
bool near(float a,float b,float tolerance=0.05f){return std::fabs(a-b)<=tolerance;}
int main() {
    constexpr float period=0.1f;
    float hz[analysis_bands];
    for (size_t b=0;b<analysis_bands;++b) hz[b]=100.0f*(b+1);
    // 60 s: background -50 dB with a flat -80 dB spectrum and a steady tone in band 20 (+12 dB).
    // Event 1: 10.0-12.0 s at -30 dB, band 30 rises 25 dB. Event 2: 40.0-40.5 s at -35 dB, band 5 rises 20 dB,
    // with a 0.2 s dip below threshold inside it (merged). A 0.2 s blip at 50 s is too short to count.
    std::vector<Frame> frames(600);
    for (size_t i=0;i<frames.size();++i) {
        Frame& f=frames[i];f.level_db=-50;
        for (size_t b=0;b<analysis_bands;++b) f.band_db[b]=-80;
        f.band_db[20]=-68;
        if (i>=100 && i<120) {f.level_db=-30;f.band_db[30]=-55;}
        if ((i>=400 && i<402) || (i>=404 && i<406)) {f.level_db=-35;f.band_db[5]=-60;}
        if (i>=500 && i<502) f.level_db=-20;
    }
    frames[250].level_db=-45; // loudest non-event frame stays below threshold
    std::vector<float> scratch(frames.size());
    Analysis a{};
    assert(analyze(frames.data(),frames.size(),period,hz,scratch.data(),a));
    assert(a.frames==600 && near(a.duration_s,60));
    assert(near(a.background_db,-50) && near(a.threshold_db,-40));
    assert(near(a.max_db,-20) && near(a.max_at_s,50));
    assert(a.loud_db>=-50 && a.loud_db<=-30);
    assert(a.average_db>-50 && a.average_db<-30);
    assert(a.event_count==2);
    assert(near(a.events[0].start_s,10) && near(a.events[0].duration_s,2) && near(a.events[0].peak_over_db,20));
    assert(near(a.events[0].band_hz,3100) && near(a.events[0].band_rise_db,25,0.2f));
    assert(near(a.events[1].start_s,40) && near(a.events[1].duration_s,0.6f) && near(a.events[1].peak_over_db,15));
    assert(near(a.events[1].band_hz,600));
    assert(a.tone_count==1 && near(a.tones[0].hz,2100) && near(a.tones[0].above_db,12));
    assert(near(a.strongest_background_hz,2100));

    // Too short to analyze.
    Analysis empty{};
    assert(!analyze(frames.data(),5,period,hz,scratch.data(),empty));

    // Level strip: loudest frame per bucket.
    float levels[10]={1,5,2,2,9,3,4,4,4,0},strip[3];
    bucket_max(levels,10,strip,3);
    assert(strip[0]==5 && strip[1]==9 && strip[2]==4);

    char text[32];
    clock_text(0,text,sizeof(text));assert(!strcmp(text,"0:00"));
    clock_text(102.4f,text,sizeof(text));assert(!strcmp(text,"1:42"));
    hz_text(250,text,sizeof(text));assert(!strcmp(text,"250 Hz"));
    hz_text(2480,text,sizeof(text));assert(!strcmp(text,"2.5 kHz"));
    hz_text(12600,text,sizeof(text));assert(!strcmp(text,"13 kHz"));
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
