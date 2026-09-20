import json
import math
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

from tools.audio_reference import spectrum


class SpectrumKernelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        root = Path(__file__).resolve().parents[1]
        cls.binary = Path(cls.directory.name)/'spectrum'
        source = Path(cls.directory.name)/'driver.cpp'
        source.write_text(r'''
#include "spectrum.h"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <vector>
int main() {
    SpectrumWorkspace workspace;
    float amplitudes[1025];
    SpectrumResult result;
    int16_t input[8192], before[8192];
    size_t frames; unsigned channels, slot;
    if (scanf("%zu %u %u", &frames, &channels, &slot) != 3) return 2;
    if (frames*channels > 8192) return 2;
    for (size_t i=0; i<frames*channels; ++i) {
        int sample;
        if (scanf("%d", &sample) != 1) return 2;
        input[i] = sample;
    }
    memcpy(before, input, frames*channels*2);
    bool ok = spectrum_pcm16(input, frames, channels, slot, workspace, amplitudes, 1025, result);
    assert(memcmp(before, input, frames*channels*2)==0);
    assert(!spectrum_pcm16(input, 32, 4, 4, workspace, amplitudes, 1025, result));
    assert(!spectrum_pcm16(input, 32, 4, 0, workspace, amplitudes, 2, result));
    assert(!spectrum_pcm16(input, 32, 4, 0, workspace, reinterpret_cast<float*>(input), 1025, result));
    assert(!spectrum_pcm16(reinterpret_cast<int16_t*>(&workspace), 32, 4, 0,
                          workspace, amplitudes, 1025, result));
    // Recompute after validation probes; all invalid calls must preserve source.
    assert(memcmp(before, input, frames*channels*2)==0);
    if (ok) ok=spectrum_pcm16(input, frames, channels, slot, workspace, amplitudes, 1025, result);
    if (!ok) { puts("{\"ok\":false}"); return 0; }
    printf("{\"ok\":true,\"peak_bin\":%d,\"clipped\":%zu,\"amplitudes\":[", result.peak_bin, result.clipped_samples);
    for (size_t i=0;i<=frames/2;++i) printf("%s%.9g",i ? ",":"",amplitudes[i]);
    puts("]}");
}
''')
        subprocess.run(['clang++', '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror',
                        '-I', str(root/'firmware/main'), str(source),
                        str(root/'firmware/main/spectrum.cpp'), '-o', str(cls.binary)],
                       check=True, capture_output=True)

    def run_kernel(self, samples, channels=1, slot=0):
        frames = len(samples)//channels
        request = f'{frames} {channels} {slot}\n'+' '.join(map(str,samples))+'\n'
        result = subprocess.run([str(self.binary)], input=request, text=True,
                                capture_output=True, check=True)
        return json.loads(result.stdout)

    def test_four_full_size_fixtures_match_independent_dft(self):
        size = 2048
        cases = {
            'tone':[round(8192*math.sin(2*math.pi*37*n/size)) for n in range(size)],
            'mixture':[round(8192*math.sin(2*math.pi*37*n/size)
                              +4096*math.sin(2*math.pi*131*n/size)) for n in range(size)],
            'silence':[0]*size,
            'impulse':[16384 if n==size//2 else 0 for n in range(size)]}
        for name, samples in cases.items():
            with self.subTest(name=name):
                expected = spectrum([x/32768 for x in samples],48000)
                actual = self.run_kernel(samples)
                self.assertTrue(actual['ok'])
                self.assertEqual(actual['clipped'],0)
                self.assertLess(max(abs(a-b) for a,b in zip(actual['amplitudes'],expected['amplitude_fs'])),1e-5)
                if expected['peak_bin'] is None:
                    self.assertEqual(actual['peak_bin'],-1)
                else:
                    self.assertEqual(actual['peak_bin'],expected['peak_bin'])
                    peak = actual['amplitudes'][actual['peak_bin']]
                    self.assertLess(abs(peak/expected['peak_amplitude_fs']-1),.01)

    def test_selected_slot_and_clipping_are_explicit(self):
        samples = [x for n in range(32) for x in (32767,0,-32768,0)]
        zero = self.run_kernel(samples,4,1)
        self.assertEqual(zero['clipped'],0)
        self.assertEqual(zero['peak_bin'],-1)
        negative = self.run_kernel(samples,4,2)
        self.assertEqual(negative['clipped'],32)
        self.assertAlmostEqual(negative['amplitudes'][0],1,places=6)

    def test_non_power_of_two_is_rejected(self):
        self.assertFalse(self.run_kernel([0]*31)['ok'])
