"""Comparison level = median of 100 ms windows (G-0002.01 Open 1, 2026-09-24).

Brief loud moments (a TV line, a door) swung the whole-capture RMS by up to
8.8 dB between A and A again; the median of short windows ignores them.
"""
import hashlib
import math
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

from tools.investigation import CaptureEvidence, MockProvider, comparison, validate_request
from test_investigation import fixture


def capture(key, level, frames=48000, burst=None, start=100, silent_windows=0):
    """Square wave of `level` counts on slot 0; optional loud burst (start, length, level)."""
    samples = []
    for i in range(frames):
        value = level if i % 2 else -level
        if i < silent_windows * 4800:
            value = 0
        if burst and burst[0] <= i < burst[0] + burst[1]:
            value = burst[2] if i % 2 else -burst[2]
        samples.append(value)
    raw = b''.join(struct.pack('<hhhh', v, 3, -3, 0) for v in samples)
    meta = dict(status='complete', boot_id='boot', session_id='session', capture_id=key,
                format='pcm_s16le', sample_rate_hz=48000, channels=4, frames=frames, gain_db=24,
                source_slot=0, physical_slot='farther-hole', speaker_active=False,
                driver_epoch_integrity=True, acquisition_start_us=start, acquisition_end_us=start + 1000000,
                size_bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    return CaptureEvidence.from_pcm(meta, raw)


def dbfs(level):
    return 20 * math.log10(level / 32768)


class MedianLevelTests(unittest.TestCase):
    def test_median_ignores_a_brief_loud_moment(self):
        steady = capture('a', 100)
        loud = capture('b', 100, burst=(9600, 2400, 10000))  # 50 ms at +40 dB in one window
        self.assertAlmostEqual(steady.measurement['median_dbfs'], dbfs(100))
        self.assertAlmostEqual(loud.measurement['median_dbfs'], dbfs(100))
        self.assertGreater(loud.measurement['rms_dbfs'], dbfs(100) + 20)

    def test_comparison_uses_the_median_level(self):
        a = capture('a', 1000).to_dict()
        b = capture('b', 500, burst=(0, 4800, 20000), start=2000000).to_dict()
        again = capture('r', 1000, start=4000000).to_dict()
        result = comparison([a, b, again])
        self.assertAlmostEqual(result['rms_delta_db'], dbfs(500) - dbfs(1000))
        self.assertAlmostEqual(result['repeat_delta_db'], 0)
        self.assertIn('median', result['unit'])

    def test_even_window_count_uses_the_mean_of_the_middle_powers(self):
        # Ten windows: five at 100 and five at 300 counts.
        item = capture('a', 100, burst=(24000, 24000, 300))
        self.assertAlmostEqual(item.measurement['median_dbfs'], 10 * math.log10((100 ** 2 + 300 ** 2) / 2 / 32768 ** 2))

    def test_mostly_silent_capture_has_no_median_and_is_inconclusive(self):
        silent = capture('b', 500, silent_windows=6, start=2000000)
        self.assertIsNone(silent.measurement['median_dbfs'])
        result = comparison([capture('a', 1000).to_dict(), silent.to_dict()])
        self.assertEqual(result['status'], 'inconclusive')
        self.assertIsNone(result['rms_delta_db'])

    def test_short_capture_is_one_window(self):
        item = capture('a', 250, frames=960)
        self.assertAlmostEqual(item.measurement['median_dbfs'], dbfs(250))

    def test_request_requires_a_consistent_median(self):
        f = fixture().to_dict(); f['frames'] = 48000
        request = dict(version=1, type='guide', boot_id='boot', session_id='session', request_id='r1',
                       deadline_ms=15100, fixture=f, adjustment=None, operator_question=None,
                       captures=[capture('a', 100).to_dict()])
        validate_request(request)
        request['captures'][0]['measurement']['median_dbfs'] = 'loud'
        with self.assertRaises(Exception):
            validate_request(request)
        del request['captures'][0]['measurement']['median_dbfs']
        with self.assertRaises(Exception):
            validate_request(request)

    def test_mock_compare_names_the_median_level(self):
        f = fixture().to_dict(); f['frames'] = 48000
        request = dict(version=1, type='compare', boot_id='boot', session_id='session', request_id='r2',
                       deadline_ms=15100, fixture=f, adjustment='Moved to B', operator_question=None,
                       captures=[capture('a', 1000).to_dict(), capture('b', 500, start=2000000).to_dict()])
        self.assertIn('median level', MockProvider().respond(request)['text'])

    def test_device_and_host_compute_the_same_median(self):
        cjson = Path('.tools/esp-idf/components/json/cJSON')
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            (p / 'driver.cpp').write_text(r'''
#include "level_median.h"
#include <cstdio>
#include <vector>
int main(){
 std::vector<int16_t> pcm;int16_t v;
 while(fread(&v,2,1,stdin)==1)pcm.push_back(v);
 const double db=median_window_dbfs(pcm.data(),pcm.size()/4,4,0);
 printf("%.12f\n",db);
}''')
            r = subprocess.run(['clang++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-I', 'firmware/main',
                                str(p / 'driver.cpp'), '-o', str(p / 'median')], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            for item in (capture('a', 100, burst=(9600, 2400, 10000)), capture('b', 100, burst=(24000, 24000, 300)),
                         capture('c', 77, frames=144000, burst=(70000, 9000, 4000))):
                out = subprocess.run([str(p / 'median')], input=item.raw, capture_output=True).stdout.decode()
                self.assertAlmostEqual(float(out), item.measurement['median_dbfs'], places=9)
            silent = capture('d', 500, silent_windows=6)
            out = subprocess.run([str(p / 'median')], input=silent.raw, capture_output=True).stdout.decode()
            self.assertEqual(out.strip(), 'nan')


if __name__ == '__main__':
    unittest.main()
