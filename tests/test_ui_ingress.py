"""Panel submission observer preserves driver behavior and retains bounded evidence."""
from pathlib import Path
import subprocess
import tempfile
import unittest

class UiIngressTests(unittest.TestCase):
    def test_panel_calls_identity_failures_and_overflow(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)
            (p/'esp_lcd_panel_ops.h').write_text('#pragma once\nusing esp_lcd_panel_handle_t=void*;using esp_err_t=int;\n')
            (p/'esp_timer.h').write_text('#include <cstdint>\nextern int64_t fake_time;inline int64_t esp_timer_get_time(){return ++fake_time;}\n')
            (p/'test.cpp').write_text(r'''
#include "ui_ingress.h"
#include <cassert>
int64_t fake_time=100;int calls=0,result=0;
extern "C" int __wrap_esp_lcd_panel_draw_bitmap(void*,int,int,int,int,const void*);
extern "C" int __real_esp_lcd_panel_draw_bitmap(void* panel,int x1,int y1,int x2,int y2,const void* pixels) {
 assert(panel==reinterpret_cast<void*>(5));assert(x1==1 && y1==2 && x2==3 && y2==4);
 assert(pixels==reinterpret_cast<void*>(6));++calls;return result;
}
void draw() {assert(__wrap_esp_lcd_panel_draw_bitmap(reinterpret_cast<void*>(5),1,2,3,4,reinterpret_cast<void*>(6))==result);}
int main() {
 draw();assert(calls==1);
 UiSubmissionRow rows[2]{};UiIngress log(rows,2,100);
 ui_observe(&log);log.animation(7,101);log.render();log.flush(true);
 draw();assert(log.count()==1 && log.submissions()==1 && log.overflow()==0);
 assert(rows[0].render==1 && rows[0].generation==7 && rows[0].changed_us==1 && rows[0].last==1);
 assert(rows[0].submitted_us<=rows[0].returned_us && rows[0].x1==1 && rows[0].y2==4);
 log.animation(8,110); // An in-progress render keeps the old generation.
 result=-9;draw();assert(rows[1].generation==7 && rows[1].result==-9);
 log.render();log.flush(false);draw();assert(log.count()==2 && log.submissions()==3 && log.overflow()==1);
 ui_observe(nullptr);draw();assert(log.submissions()==3 && calls==5);
}
''')
            subprocess.run(['clang++','-std=c++17','-Wall','-Wextra','-Werror','-I',str(p),'-I','firmware/main',
                            str(p/'test.cpp'),'firmware/main/ui_ingress.cpp','-o',str(p/'test')],check=True,capture_output=True)
            subprocess.run([str(p/'test')],check=True)
