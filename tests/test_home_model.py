import shutil
import subprocess
import tempfile
from pathlib import Path
import unittest


class HomeModelTests(unittest.TestCase):
    def test_tiles_readings_and_labels(self):
        compiler = shutil.which('clang++') or shutil.which('g++')
        self.assertIsNotNone(compiler)
        source = r'''
#include "home_model.h"
#include <cassert>
#include <cmath>
#include <cstring>
int main() {
    using namespace home;
    // Eight tiles fill the screen below the header, in bounds, without overlap, at least 250 px.
    for (unsigned i=0;i<tile_count;++i) {
        const Rect a=tile(i);
        assert(a.w>=250 && a.h>=250);
        assert(a.x>=0 && a.y>=header && a.x+a.w<=screen_w && a.y+a.h<=screen_h);
        for (unsigned j=i+1;j<tile_count;++j) {
            const Rect b=tile(j);
            assert(a.x+a.w<=b.x || b.x+b.w<=a.x || a.y+a.h<=b.y || b.y+b.h<=a.y);
        }
    }
    assert(tile(0).x==tile(4).x && tile(0).y<tile(4).y);
    assert(tile(0).y==tile(3).y && tile(0).x<tile(3).x);

    // Tilt from lying flat, independent of units and screen up/down.
    assert(std::fabs(tilt_degrees(0,0,1000))<0.01f);
    assert(std::fabs(tilt_degrees(0,0,-1000))<0.01f);
    assert(std::fabs(tilt_degrees(1000,0,0)-90)<0.01f);
    assert(std::fabs(tilt_degrees(0,700,700)-45)<0.01f);
    assert(std::isnan(tilt_degrees(0,0,0)));

    char text[64];
    motion_text(12.4f,text,sizeof(text));assert(!strcmp(text,"Tilt 12\xc2\xb0"));
    motion_text(NAN,text,sizeof(text));assert(!strcmp(text,"No data"));
    // INA226 battery branch: negative current flows into the battery.
    power_text(8.36f,-0.061f,text,sizeof(text));assert(!strcmp(text,"8.36 V\nCharging 0.06 A"));
    power_text(8.10f,0.42f,text,sizeof(text));assert(!strcmp(text,"8.10 V\nUsing 0.42 A (3.4 W)"));
    power_text(8.36f,0.004f,text,sizeof(text));assert(!strcmp(text,"8.36 V\nNo battery current"));
    power_text(NAN,0,text,sizeof(text));assert(!strcmp(text,"No data"));
    network_text(0,text,sizeof(text));assert(!strcmp(text,"Wi-Fi offline"));
    network_text(0x0a0a14ac,text,sizeof(text));assert(!strcmp(text,"Wi-Fi 172.20.10.10"));
    // F-0003 hotspot mode: the device's own network, and whether the Mac has joined.
    network_text(0,0,false,text,sizeof(text));assert(!strcmp(text,"Wi-Fi offline"));
    network_text(0x0a0a14ac,0,false,text,sizeof(text));assert(!strcmp(text,"Wi-Fi 172.20.10.10"));
    network_text(0,0,true,text,sizeof(text));assert(!strcmp(text,"Hotspot starting"));
    network_text(0x0104a8c0,0,true,text,sizeof(text));assert(!strcmp(text,"Hotspot on\nWaiting for the Mac"));
    network_text(0x0104a8c0,0x0204a8c0,true,text,sizeof(text));assert(!strcmp(text,"Hotspot on\nMac 192.168.4.2"));
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
