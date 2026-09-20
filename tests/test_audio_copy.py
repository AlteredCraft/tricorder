"""Exercise the firmware's playback copy using the host C++ compiler."""
from pathlib import Path
import subprocess
import tempfile
import unittest


class AudioCopyTests(unittest.TestCase):
    def test_playback_preserves_signed_slots_and_raw_source(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'test.cpp'
            binary = Path(directory)/'test'
            source.write_text(r'''
#include "audio_copy.h"
#include <cassert>
#include <cstring>
int main() {
    const int16_t raw[] = {-32768, -1, 0, 32767, 11, 22, 33, 44};
    int16_t saved[8], out[4];
    memcpy(saved, raw, sizeof(raw));
    for (unsigned slot=0; slot<4; ++slot) {
        assert(audio_slot_stereo(raw, 2, slot, out, 4));
        assert(out[0] == raw[slot] && out[1] == raw[slot]);
        assert(out[2] == raw[4+slot] && out[3] == raw[4+slot]);
        memset(out, 0, sizeof(out)); // Model in-place codec volume processing.
        assert(memcmp(raw, saved, sizeof(raw)) == 0);
    }
    out[0] = 123;
    assert(!audio_slot_stereo(raw, 2, 4, out, 4));
    assert(!audio_slot_stereo(raw, 2, 0, out, 3));
    assert(out[0] == 123);
}
''')
            subprocess.run(['clang++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                            '-I', str(root/'firmware/main'), str(source), '-o', str(binary)],
                           check=True, capture_output=True)
            subprocess.run([str(binary)], check=True)
