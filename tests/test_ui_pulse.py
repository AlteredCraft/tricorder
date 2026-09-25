"""LVGL probe-timer intervals during sessions (firmware/main/ui_pulse.h, G-0001.02 C2)."""
from pathlib import Path
import subprocess
import tempfile
import unittest

DRIVER = r'''
#include "ui_pulse.h"
#include <cassert>
#include <cstdio>
int main() {
    UiPulse p;
    assert(p.count()==0 && p.max_us()==0 && p.percentile_ms(0.95)==0);
    p.tick(1000); // the first tick only sets the phase
    assert(p.count()==0);
    int64_t now=1000;
    for(int i=0;i<94;++i){now+=20000;p.tick(now);}       // 94 x 20 ms
    for(int i=0;i<5;++i){now+=45500;p.tick(now);}        // 5 x 45.5 ms
    now+=250000;p.tick(now);                              // 1 x 250 ms
    assert(p.count()==100);
    assert(p.percentile_ms(0.50)==20);
    assert(p.percentile_ms(0.95)==46);                    // bins round up to whole ms
    assert(p.percentile_ms(1.0)==250);
    assert(p.max_us()==250000);
    assert(p.over_ms(50)==1 && p.over_ms(200)==1 && p.over_ms(20)==6);
    now+=5000000;p.tick(now);                             // beyond the last bin
    assert(p.max_us()==5000000 && p.percentile_ms(1.0)==1001 && p.over_ms(1000)==1);
    p.reset();
    assert(p.count()==0 && p.max_us()==0);
    p.tick(10);p.tick(10);                                // zero interval is still an interval
    assert(p.count()==1 && p.percentile_ms(0.5)==0);
    puts("ok");
}
'''


class UiPulseTests(unittest.TestCase):
    def test_histogram_percentiles_and_overflow(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'driver.cpp').write_text(DRIVER)
            result = subprocess.run(['clang++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                                     '-fsanitize=address,undefined', '-I', 'firmware/main',
                                     str(root / 'driver.cpp'), '-o', str(root / 'driver')],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(root / 'driver')], capture_output=True, text=True, timeout=10)
            self.assertEqual((result.returncode, result.stdout.strip()), (0, 'ok'), result.stderr)


if __name__ == '__main__':
    unittest.main()
