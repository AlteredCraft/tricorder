"""Keep animation deadlines on elapsed time instead of accumulating timer rounding."""
from pathlib import Path
import tempfile,subprocess,unittest
class UiScheduleTests(unittest.TestCase):
    def test_rounding_compensation_and_missed_deadlines(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);(p/'test.cpp').write_text(r'''
#include "ui_schedule.h"
#include <cassert>
int main() {
 UiSchedule s(1000000);
 assert(s.after_tick(1035000)==31 && s.missed()==0);
 assert(s.after_tick(1070000)==29 && s.missed()==0);
 assert(s.after_tick(1100000)==32 && s.missed()==0);
 assert(s.after_tick(1190000)==8 && s.missed()==1);
}
''')
            subprocess.run(['clang++','-std=c++17','-Wall','-Wextra','-Werror','-I','firmware/main',str(p/'test.cpp'),'-o',str(p/'test')],check=True,capture_output=True)
            subprocess.run([str(p/'test')],check=True)
