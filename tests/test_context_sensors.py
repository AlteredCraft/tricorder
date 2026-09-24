"""Steadiness window and context-shot downsample, compiled natively under ASan."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def build(source):
    directory = tempfile.TemporaryDirectory()
    path = Path(directory.name)
    (path/'driver.cpp').write_text(source)
    subprocess.run(['clang++', '-std=c++17', '-O1', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', '-I', str(ROOT/'firmware/main'),
                    str(path/'driver.cpp'), '-o', str(path/'driver')],
                   check=True, capture_output=True)
    return directory, path/'driver'


class SteadinessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory, cls.binary = build(r'''
#include "steadiness.h"
#include <cstdio>
// stdin: lines "a t gx gy gz ax ay az" (add), "f t" (failed read), "r t" (read)
int main() {
    Steadiness s;char op;
    while (scanf(" %c",&op)==1) {
        unsigned t;scanf("%u",&t);
        if (op=='a') {int g[3],a[3];scanf("%d %d %d %d %d %d",g,g+1,g+2,a,a+1,a+2);
            int16_t gg[3]={int16_t(g[0]),int16_t(g[1]),int16_t(g[2])},aa[3]={int16_t(a[0]),int16_t(a[1]),int16_t(a[2])};
            s.add(t,gg,aa);}
        else if (op=='f') s.fail(t);
        else {auto r=s.read(t);
            printf("{\"state\":%d,\"peak_dps\":%.4f,\"span_g\":%.5f,\"samples\":%u}\n",
                   static_cast<int>(r.state),r.peak_dps,r.accel_span_g,r.samples);}
    }
}
''')
        cls.addClassCleanup(cls.directory.cleanup)

    def run_ops(self, ops):
        out = subprocess.run([str(self.binary)], input='\n'.join(ops)+'\n', text=True,
                             capture_output=True, check=True).stdout
        return [json.loads(line) for line in out.splitlines()]

    UNKNOWN, STEADY, MOVING = 0, 1, 2

    @staticmethod
    def samples(start, count, gyro=(0, 0, 0), accel=(0, 0, 8192), step=40):
        return [f'a {start+i*step} {gyro[0]} {gyro[1]} {gyro[2]} {accel[0]} {accel[1]} {accel[2]}'
                for i in range(count)]

    def test_no_samples_is_unknown(self):
        self.assertEqual(self.run_ops(['r 1000'])[0]['state'], self.UNKNOWN)

    def test_hand_tremor_level_is_steady(self):
        # 2 dps on one axis (65 LSB at 32.768 LSB/dps), gravity on z.
        ops = self.samples(0, 13, gyro=(65, 0, 0))+['r 490']
        r = self.run_ops(ops)[0]
        self.assertEqual(r['state'], self.STEADY)
        self.assertAlmostEqual(r['peak_dps'], 65/32.768, places=3)
        self.assertEqual(r['samples'], 13)

    def test_rotation_is_moving_and_uses_vector_magnitude(self):
        # 3 dps per axis is 5.2 dps as a vector: above the 4 dps limit.
        r = self.run_ops(self.samples(0, 13, gyro=(98, 98, 98))+['r 500'])[0]
        self.assertEqual(r['state'], self.MOVING)
        self.assertAlmostEqual(r['peak_dps'], (3*98**2)**.5/32.768, places=3)

    def test_linear_jolt_without_rotation_is_moving(self):
        ops = self.samples(0, 6)+self.samples(240, 1, accel=(0, 0, 9000))+self.samples(280, 6)+['r 500']
        r = self.run_ops(ops)[0]
        self.assertEqual(r['state'], self.MOVING)
        self.assertAlmostEqual(r['span_g'], (9000-8192)/8192, places=4)

    def test_motion_ages_out_of_the_half_second_window(self):
        ops = self.samples(0, 5, gyro=(2000, 0, 0))+self.samples(200, 20)+['r 400', 'r 1000']
        during, after = self.run_ops(ops)
        self.assertEqual(during['state'], self.MOVING)
        self.assertEqual(after['state'], self.STEADY)

    def test_too_few_or_stale_samples_are_unknown(self):
        few = self.run_ops(self.samples(0, 3)+['r 100'])[0]
        stale = self.run_ops(self.samples(0, 13)+['r 800'])[0]
        self.assertEqual(few['state'], self.UNKNOWN)
        self.assertEqual(stale['state'], self.UNKNOWN)

    def test_read_failure_clears_the_window(self):
        ops = self.samples(0, 13)+['f 500', 'r 510']
        self.assertEqual(self.run_ops(ops)[0]['state'], self.UNKNOWN)

    def test_ring_keeps_only_recent_samples(self):
        # Overflowing the bounded ring must not corrupt the window.
        ops = self.samples(0, 100, gyro=(2000, 0, 0), step=5)+self.samples(500, 100, step=10)+['r 1490']
        r = self.run_ops(ops)[0]
        self.assertEqual(r['state'], self.STEADY)


class DownsampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory, cls.binary = build(r'''
#include "image_downsample.h"
#include <cassert>
#include <cstdio>
#include <vector>
static uint16_t rgb(unsigned r,unsigned g,unsigned b){return uint16_t((r<<11)|(g<<5)|b);}
int main() {
    // 8x4 source, factor 4 -> 2x1. Left block: half white half black rows.
    std::vector<uint16_t> src(8*4,0),dst(2);
    for (unsigned y=0;y<2;++y) for (unsigned x=0;x<4;++x) src[y*8+x]=rgb(31,63,31);
    for (unsigned y=0;y<4;++y) for (unsigned x=4;x<8;++x) src[y*8+x]=rgb(31,0,0);
    assert(rgb565_downsample(src.data(),src.size()*2,8,4,4,dst.data(),dst.size()*2));
    printf("%u %u %u %u %u %u\n",dst[0]>>11,(dst[0]>>5)&63,dst[0]&31,dst[1]>>11,(dst[1]>>5)&63,dst[1]&31);
    printf("%u %u\n",rgb565_mean_luma(src.data(),src.size()),rgb565_mean_luma(dst.data(),0));
    // Rejections: wrong sizes, non-divisible dimensions, zero factor.
    assert(!rgb565_downsample(src.data(),src.size()*2-2,8,4,4,dst.data(),dst.size()*2));
    assert(!rgb565_downsample(src.data(),src.size()*2,8,4,4,dst.data(),2));
    assert(!rgb565_downsample(src.data(),src.size()*2,8,4,3,dst.data(),dst.size()*2));
    assert(!rgb565_downsample(src.data(),src.size()*2,8,4,0,dst.data(),dst.size()*2));
    assert(!rgb565_downsample(nullptr,src.size()*2,8,4,4,dst.data(),dst.size()*2));
    // Tab5 native 1280x720 -> 320x180 is accepted.
    std::vector<uint16_t> big(1280*720,rgb(0,63,0)),small(320*180);
    assert(rgb565_downsample(big.data(),big.size()*2,1280,720,4,small.data(),small.size()*2));
    assert(small[0]==rgb(0,63,0) && small.back()==rgb(0,63,0));
}
''')
        cls.addClassCleanup(cls.directory.cleanup)

    def test_box_average_luma_and_bounds(self):
        out = subprocess.run([str(self.binary)], text=True, capture_output=True, check=True).stdout.split('\n')
        # Half white, half black block averages each channel to half scale (rounded).
        self.assertEqual(out[0], '16 32 16 31 0 0')
        # Luma: white 255 for 8 px, red 76 for 16 px, black 0 for 8 px over 32 px; empty is 0.
        self.assertEqual(out[1], f'{round((8*255+16*76)/32)} 0')


if __name__ == '__main__':
    unittest.main()
