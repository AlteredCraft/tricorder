import json
import math
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.audio_reference import spectrum


def lcg_noise(count, seed=1, scale=4000):
    state, out = seed, []
    for _ in range(count):
        state = (1103515245*state+12345) % 2**31
        out.append(round(scale*(state/2**30-1)))
    return out


class SpectrumDisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        root = Path(__file__).resolve().parents[1]
        cls.binary = Path(cls.directory.name)/'bands'
        source = Path(cls.directory.name)/'driver.cpp'
        source.write_text(r'''
#include "spectrum_display.h"
#include <cstdio>
#include <string>
#include <vector>
int main() {
    char mode[16];
    if (scanf("%15s", mode)!=1) return 2;
    std::string m(mode);
    if (m=="edges") {
        printf("[");
        for (size_t i=0;i<=spectrum_band_count;++i) printf("%s%.9g",i?",":"",spectrum_band_edge_hz(i));
        puts("]");return 0;
    }
    if (m=="chart") {
        float db;printf("[");
        for (int i=0;scanf("%f",&db)==1;++i) printf("%s%d",i?",":"",static_cast<int>(spectrum_chart_value(db)));
        puts("]");return 0;
    }
    size_t frames,window;unsigned channels,slot;
    if (scanf("%zu %u %u %zu",&frames,&channels,&slot,&window)!=4) return 2;
    std::vector<int16_t> pcm(frames*channels);
    for (auto& s:pcm){int v;if(scanf("%d",&v)!=1)return 2;s=v;}
    static SpectrumWorkspace workspace;static float amplitudes[spectrum_max_frames/2+1];
    SpectrumBands bands;
    bool ok=spectrum_bands_pcm16(pcm.data(),frames,channels,slot,window,48000,workspace,
                                 amplitudes,spectrum_max_frames/2+1,bands);
    if (!ok){puts("{\"ok\":false}");return 0;}
    float db[spectrum_band_count];spectrum_bands_db(bands,db);
    printf("{\"ok\":true,\"windows\":%u,\"db\":[",bands.windows);
    for (size_t i=0;i<spectrum_band_count;++i) printf("%s%.9g",i?",":"",db[i]);
    puts("]}");
}
''')
        subprocess.run(['clang++', '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror',
                        '-fsanitize=address,undefined', '-I', str(root/'firmware/main'), str(source),
                        str(root/'firmware/main/spectrum_display.cpp'),
                        str(root/'firmware/main/spectrum.cpp'), '-o', str(cls.binary)],
                       check=True, capture_output=True)
        cls.edges = cls.run_driver('edges\n')
        cls.count = len(cls.edges)-1

    @classmethod
    def run_driver(cls, request):
        result = subprocess.run([str(cls.binary)], input=request, text=True,
                                capture_output=True, check=True)
        return json.loads(result.stdout)

    def bands(self, samples, channels=1, slot=0, window=2048):
        frames = len(samples)//channels
        return self.run_driver(f'bands {frames} {channels} {slot} {window}\n'
                               +' '.join(map(str, samples))+'\n')

    def band_of(self, hz):
        return next(i for i in range(self.count) if self.edges[i] <= hz < self.edges[i+1])

    def test_edges_are_log_spaced_over_the_audible_display_range(self):
        self.assertEqual(self.count, 48)
        self.assertAlmostEqual(self.edges[0], 50, places=3)
        self.assertAlmostEqual(self.edges[-1], 20000, delta=0.05)
        ratios = [b/a for a, b in zip(self.edges, self.edges[1:])]
        for r in ratios:
            self.assertAlmostEqual(r, ratios[0], places=5)

    def test_tone_peaks_in_its_band_and_stays_out_of_distant_bands(self):
        samples = [round(16384*math.sin(2*math.pi*1000*n/48000)) for n in range(8192)]
        result = self.bands(samples)
        self.assertTrue(result['ok'])
        self.assertEqual(result['windows'], 4)
        db = result['db']
        self.assertEqual(max(range(self.count), key=db.__getitem__), self.band_of(1000))
        self.assertGreater(db[self.band_of(1000)], -20)
        self.assertLess(db[self.band_of(100)], db[self.band_of(1000)]-60)
        self.assertLess(db[self.band_of(10000)], db[self.band_of(1000)]-60)

    def test_silence_is_the_display_floor(self):
        result = self.bands([0]*4096)
        self.assertTrue(result['ok'])
        self.assertEqual(result['db'], [-110.0]*self.count)

    def test_white_noise_is_flat_after_averaging(self):
        result = self.bands(lcg_noise(48000))
        self.assertEqual(result['windows'], 23)
        above = [d for d, low in zip(result['db'], self.edges) if low >= 200]
        self.assertLess(max(above)-min(above), 6)

    def test_selects_the_requested_interleaved_slot(self):
        tone = [round(16384*math.sin(2*math.pi*5000*n/48000)) for n in range(4096)]
        noise = lcg_noise(4096, seed=7, scale=200)
        interleaved = [v for pair in zip(noise, tone, noise, noise) for v in pair]
        on_tone = self.bands(interleaved, channels=4, slot=1)['db']
        on_noise = self.bands(interleaved, channels=4, slot=0)['db']
        self.assertEqual(max(range(self.count), key=on_tone.__getitem__), self.band_of(5000))
        self.assertLess(on_noise[self.band_of(5000)], on_tone[self.band_of(5000)]-30)

    def test_matches_independent_reference_band_average(self):
        samples = lcg_noise(2048, seed=3)
        amplitude = spectrum([x/32768 for x in samples], 48000)['amplitude_fs']
        expected = []
        for low, high in zip(self.edges, self.edges[1:]):
            bins = [k for k in range(len(amplitude)) if low <= k*48000/2048 < high]
            if not bins:
                center = math.sqrt(low*high)
                bins = [round(center*2048/48000)]
            power = sum(amplitude[k]**2 for k in bins)/len(bins)
            expected.append(max(-110, 10*math.log10(power)) if power else -110)
        actual = self.bands(samples)['db']
        for e, a in zip(expected, actual):
            self.assertAlmostEqual(e, a, delta=0.01)

    def test_rejects_invalid_shapes(self):
        self.assertFalse(self.bands([0]*1024)['ok'])  # shorter than one window
        self.assertFalse(self.bands([0]*4096, channels=2, slot=2)['ok'])
        self.assertFalse(self.bands([0]*4096, window=3000)['ok'])  # not a power of two

    def test_chart_value_clamps_to_display_range(self):
        self.assertEqual(self.run_driver('chart\n-200 -110 -70 -30 0\n'), [0, 0, 50, 100, 100])


if __name__ == '__main__':
    unittest.main()
