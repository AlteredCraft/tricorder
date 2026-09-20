"""Exercise the actual C++ speech conditioner with independent signal checks."""
from pathlib import Path
import subprocess
import tempfile
import unittest


class SpeechFilterTests(unittest.TestCase):
    def test_ownership_block_boundaries_and_filter_response(self):
        source=r'''
#include "speech_filter.h"
#include <cassert>
#include <cmath>
#include <cstring>
#include <vector>

double rms(double frequency) {
    SpeechFilter filter(true,1,0);
    int16_t input[480], output[480];
    SpeechBlockResult result;
    double energy=0; size_t count=0;
    for (unsigned block=0;block<100;++block) {
        for (unsigned i=0;i<480;++i)
            input[i]=frequency ? std::lround(8192*std::sin(2*3.141592653589793*frequency*(block*480+i)/48000)) : 4000;
        assert(filter.process(input,480,output,480,result));
        assert(result.source_start==block*480 && result.source_frames==480 && result.output_frames==160);
        if (block>=50) for (size_t i=0;i<result.output_frames;++i) {energy+=double(output[i])*output[i];++count;}
    }
    return std::sqrt(energy/count);
}

int main() {
    int16_t raw[2048*4], saved[2048*4], output[2048];
    for (int i=0;i<2048*4;++i) raw[i]=int16_t(i*173-32768);
    memcpy(saved,raw,sizeof(raw));
    SpeechBlockResult result;
    SpeechFilter bypass(false,4,2);
    assert(bypass.process(raw,2048,output,2048,result));
    assert(result.output_frames==2048 && result.source_start==0);
    for (int i=0;i<2048;++i) assert(output[i]==raw[i*4+2]);
    memset(output,0,sizeof(output));
    assert(memcmp(raw,saved,sizeof(raw))==0);
    SpeechFilter whole(true,4,0), chunked(true,4,0);
    int16_t expected[2048];
    assert(whole.process(raw,2048,expected,2048,result));
    size_t total=result.output_frames,offset=0,written=0;
    for (size_t chunk: {size_t(1),size_t(479),size_t(33),size_t(1024),size_t(511)}) {
        assert(chunked.process(raw+offset*4,chunk,output+written,2048-written,result));
        assert(result.source_start==offset);
        offset+=chunk;written+=result.output_frames;
    }
    assert(offset==2048 && written==total && total==682);
    assert(memcmp(expected,output,total*2)==0 && memcmp(raw,saved,sizeof(raw))==0);
    SpeechFilter rejected(true,4,0);
    assert(!rejected.process(raw,2048,raw,2048,result));
    assert(!rejected.process(raw,2048,output,1,result));
    assert(!rejected.process(nullptr,2048,output,2048,result));
    assert(rejected.process(raw,2048,output,2048,result));
    assert(result.source_start==0 && memcmp(expected,output,total*2)==0);
    SpeechFilter invalid(true,4,4);
    assert(!invalid.process(raw,2048,output,2048,result));
    const double pass=rms(1000), stop=rms(13000);
    assert(std::abs(pass/(8192/std::sqrt(2))-1)<0.02);
    assert(stop/pass<0.001); // at least 60 dB rejection at this stopband fixture
    assert(rms(0)<1);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'test.cpp').write_text(source)
            subprocess.run(['clang++','-std=c++17','-O2','-Wall','-Wextra','-Werror',
                            '-I','firmware/main',str(root/'test.cpp'),'firmware/main/speech_filter.cpp',
                            '-o',str(root/'test')],check=True,capture_output=True)
            subprocess.run([str(root/'test')],check=True)
