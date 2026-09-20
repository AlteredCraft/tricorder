"""Exercise the actual sustained audio consumer before integrating the driver loop."""
from pathlib import Path
import subprocess
import tempfile
import unittest


class AudioWorkloadTests(unittest.TestCase):
    def test_rolling_window_cadence_counters_and_ownership(self):
        source=r'''
#include "audio_workload.h"
#include <cassert>
#include <cmath>
#include <cstring>
int main() {
    AudioWorkloadConsumer consumer;
    int16_t raw[480*4],saved[480*4],speech[160];
    AudioWorkloadResult result;
    size_t spectra=0;
    for (unsigned block=0;block<200;++block) {
        for (unsigned frame=0;frame<480;++frame) {
            raw[frame*4]=std::lround(8192*std::sin(2*3.141592653589793*37*(block*480+frame)/2048));
            raw[frame*4+1]=111;raw[frame*4+2]=-222;raw[frame*4+3]=333;
        }
        memcpy(saved,raw,sizeof(raw));
        if (block==0) {
            assert(!consumer.process(raw,479,speech,160,result));
            assert(!consumer.process(raw,480,speech,159,result));
            assert(!consumer.process(raw,480,raw,160,result));
        }
        assert(consumer.process(raw,480,speech,160,result));
        assert(result.speech.source_start==block*480 && result.speech.source_frames==480);
        assert(result.speech.output_frames==160);
        assert(memcmp(raw,saved,sizeof(raw))==0);
        assert(result.fft_ready==((block+1)%5==0));
        if (result.fft_ready) {
            ++spectra;
            assert(result.fft_start_frame==(block+1)*480-2048);
            assert(result.spectrum.peak_bin==37);
            assert(std::abs(result.spectrum.peak_amplitude_fs-.25)<.0025);
        }
        // The next block may reuse the producer's buffer immediately.
        memset(raw,0,sizeof(raw));
    }
    assert(spectra==40);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'test.cpp').write_text(source)
            subprocess.run(['clang++','-std=c++17','-O2','-Wall','-Wextra','-Werror',
                            '-I','firmware/main',str(root/'test.cpp'),'firmware/main/audio_workload.cpp',
                            'firmware/main/speech_filter.cpp','firmware/main/spectrum.cpp',
                            '-o',str(root/'test')],check=True,capture_output=True)
            subprocess.run([str(root/'test')],check=True)
