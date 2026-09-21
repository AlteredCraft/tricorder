"""Replay pinned CSI queue starvation during the measured 69.540 ms source hold."""
from pathlib import Path
import subprocess
import tempfile
import unittest


class CameraBufferTests(unittest.TestCase):
    def test_native_rate_continues_while_source_is_owned(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'test.cpp').write_text(r'''
#include "camera_buffers.h"
#include <cassert>
#include <deque>

// CSI pops the next queued element before finishing the current DMA. If
// nothing is queued it reuses the current element and suppresses delivery.
unsigned replay(unsigned count) {
    std::deque<unsigned> queued;
    for (unsigned n=2;n<count;++n) queued.push_back(n);
    unsigned active=1, suppressed=0;
    std::deque<unsigned> completed;
    // Element 0 was dequeued at t=0 and is still held at t=33 and t=66 ms.
    for (unsigned time : {33333,66666,99999}) {
        if (time>69540) {
            queued.push_back(0);
            while (!completed.empty()) {
                queued.push_back(completed.front());completed.pop_front();
            }
        }
        unsigned next=active;
        if (!queued.empty()) {next=queued.front();queued.pop_front();}
        if (next==active) ++suppressed;
        else completed.push_back(active);
        active=next;
    }
    return suppressed;
}
int main() {
    assert(replay(2)==2); // Reproduces the old configuration's mechanism.
    assert(replay(camera_capture_buffer_count)==0);
    assert(camera_capture_buffer_count<=8); // Fixed observer identity capacity.
}
''')
            subprocess.run(['clang++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                            '-I', 'firmware/main', str(root / 'test.cpp'), '-o', str(root / 'test')],
                           check=True, capture_output=True)
            subprocess.run([str(root / 'test')], check=True)
