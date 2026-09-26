import shutil
import subprocess
import tempfile
from pathlib import Path
import unittest


class SoundModelTests(unittest.TestCase):
    def test_level_peak_hold_and_window(self):
        compiler = shutil.which('clang++') or shutil.which('g++')
        self.assertIsNotNone(compiler)
        source = r'''
#include "sound_model.h"
#include <cassert>
#include <cmath>
#include <cstring>
int main() {
    using namespace sound;
    // RMS level of slot 0 in dB relative to full scale; silence has a floor.
    int16_t full[8]={32767,0,0,0,-32767,0,0,0};
    assert(std::fabs(level_dbfs(full,2,4,0)-0.0f)<0.01f);
    int16_t tenth[8]={3277,0,0,0,-3277,0,0,0};
    assert(std::fabs(level_dbfs(tenth,2,4,0)+20.0f)<0.01f);
    int16_t silent[8]={};
    assert(level_dbfs(silent,2,4,0)==level_floor_db);
    int16_t other_slot[8]={0,32767,0,0,0,32767,0,0};
    assert(level_dbfs(other_slot,2,4,0)==level_floor_db);

    // Peak hold keeps the maximum per band until reset.
    float peak[3];reset_peak(peak,3);
    const float a[3]={-80,-60,-100},b[3]={-90,-50,-100};
    hold_peak(a,peak,3);hold_peak(b,peak,3);
    assert(peak[0]==-80 && peak[1]==-50 && peak[2]==-100);
    reset_peak(peak,3);assert(peak[0]<=-1000);

    // The sliding window keeps the newest frames in order across block boundaries.
    Window<8,2> w;
    int16_t block1[6*2],block2[4*2];
    for(int i=0;i<6;++i){block1[2*i]=i;block1[2*i+1]=100+i;}
    for(int i=0;i<4;++i){block2[2*i]=6+i;block2[2*i+1]=106+i;}
    assert(!w.full());
    w.push(block1,6);assert(!w.full());
    w.push(block2,4);assert(w.full());
    int16_t out[8*2];w.copy(out);
    for(int i=0;i<8;++i)assert(out[2*i]==2+i && out[2*i+1]==102+i);
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
