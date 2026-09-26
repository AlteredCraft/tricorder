import shutil
import subprocess
import tempfile
from pathlib import Path
import unittest


class SpeakerRouteTests(unittest.TestCase):
    def test_headphones_turn_off_only_the_speaker_amp(self):
        compiler = shutil.which('clang++') or shutil.which('g++')
        self.assertIsNotNone(compiler)
        source = r'''
#include "speaker_route.h"
#include <cassert>
int main() {
    using namespace speaker_route;
    assert(headphones(0x80));
    assert(headphones(0xff));
    assert(!headphones(0x7f));
    assert(!headphones(0x00));
    // The BSP boot latch 0b01100110: P1 amp, P2 ext 5 V, P5 touch reset, P6 camera reset.
    assert(output_for(0x66, true) == 0x64);
    assert(output_for(0x66, false) == 0x66);
    assert(output_for(0x64, false) == 0x66);
    assert(output_for(0x64, true) == 0x64);
    assert(output_for(0xff, true) == 0xfd);
    assert(output_for(0x00, false) == 0x02);
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
