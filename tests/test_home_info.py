import re
import shutil
import subprocess
import tempfile
from pathlib import Path
import unittest


class HomeInfoTests(unittest.TestCase):
    def test_every_working_tile_has_renderable_info(self):
        compiler = shutil.which('clang++') or shutil.which('g++')
        self.assertIsNotNone(compiler)
        source = r'''
#include "home_info.h"
#include "home_model.h"
#include <cstdio>
int main() {
    static_assert(sizeof(home::tile_text)/sizeof(home::tile_text[0])==home::tile_count);
    for (const auto& t:home::tile_text)
        std::printf("%s\x1f%s\x1f%s\x1e",t.name,t.note,t.info?t.info:"");
}
'''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'test.cpp').write_text(source)
            subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
                            '-I', 'firmware/main', str(root/'test.cpp'), '-o', str(root/'test')], check=True)
            output = subprocess.run([str(root/'test')], check=True, capture_output=True).stdout.decode('utf-8')
        tiles = [record.split('\x1f') for record in output.split('\x1e') if record]
        names = [name for name, _, _ in tiles]
        self.assertEqual(names, ['Sound', 'Motion', 'Camera', 'Power', 'Setup', 'Diagnostics'])
        for name, _, info in tiles:
            self.assertGreater(len(info.split()), 40, name)
        # Built-in Montserrat: ASCII, degree sign and bullet only.
        for name, note, info in tiles:
            for text in (name, note, info):
                bad = {c for c in text if not (c == '\n' or ' ' <= c <= '~' or c in '°•')}
                self.assertEqual(bad, set(), name)


if __name__ == '__main__':
    unittest.main()
