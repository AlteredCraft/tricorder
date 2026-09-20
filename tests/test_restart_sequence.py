import shutil
import subprocess
import tempfile
from pathlib import Path
import unittest


class RestartSequenceTests(unittest.TestCase):
    def test_bounded_sequence_and_interrupted_or_corrupt_state(self):
        compiler = shutil.which('clang++') or shutil.which('g++')
        self.assertIsNotNone(compiler)
        source = r'''
#include "restart_sequence.h"
#include <cassert>
int main() {
    RestartSequence state{};
    assert(!state.resume(true));
    state.start(123);
    for (unsigned i=1; i<=10; ++i) {
        assert(state.next() == i);
        assert(state.resume(true));
        assert(state.series() == 123);
        assert(state.completed() == i);
    }
    assert(state.next() == 0);
    assert(!state.resume(true));
    state.start(456);
    assert(state.next() == 1);
    assert(!state.resume(false));
    assert(state.next() == 0);
    state.start(789);
    state.next();
    auto *bytes = reinterpret_cast<unsigned char*>(&state);
    bytes[0] ^= 1;
    assert(!state.resume(true));
    assert(state.next() == 0);
    state.start(12);
    assert(!state.resume(true)); // start alone is not a pending reset
    assert(state.next() == 0);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'test.cpp').write_text(source)
            subprocess.run([compiler,'-std=c++17','-Wall','-Wextra','-Werror',
                            '-I','firmware/main',str(root/'test.cpp'),'-o',str(root/'test')],check=True)
            subprocess.run([str(root/'test')],check=True)
