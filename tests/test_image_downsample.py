"""RGB565 box downsample (the Camera viewfinder), compiled natively under ASan."""
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

    def test_box_average_and_bounds(self):
        out = subprocess.run([str(self.binary)], text=True, capture_output=True, check=True).stdout.split('\n')
        # Half white, half black block averages each channel to half scale (rounded).
        self.assertEqual(out[0], '16 32 16 31 0 0')


if __name__ == '__main__':
    unittest.main()
