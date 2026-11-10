import shutil
import subprocess
import tempfile
from pathlib import Path
import unittest


class PowerAnalysisTests(unittest.TestCase):
    def test_sources_draw_energy_steps_screen_changes_and_formatting(self):
        compiler = shutil.which('clang++') or shutil.which('g++')
        self.assertIsNotNone(compiler)
        source = r'''
#include "power_analysis.h"
#include <cassert>
#include <cstring>
#include <vector>
using namespace power;
bool near(float a,float b,float t){return std::fabs(a-b)<=t;}
int main() {
    // 0-20 s on battery at 0.50 A, 8.20 V; 20-40 s screen bright at 0.65 A; 40-60 s back to 0.50 A;
    // 60-70 s USB plugged in, charging at -0.40 A, 8.30 V.
    std::vector<Sample> s;std::vector<Mark> marks={{200,100},{400,50},{690,20}};
    for(size_t i=0;i<700;++i) {
        const float t=i/10.0f;Sample x{8.20f,0.50f};
        if(t>=20 && t<40)x.a=0.65f;
        if(t>=60){x.a=-0.40f;x.v=8.30f;}
        x.a+=(static_cast<int>(i%7)-3)*0.001f;
        s.push_back(x);
    }
    std::vector<float> scratch(s.size());Analysis a;
    assert(analyze(s.data(),s.size(),marks.data(),marks.size(),scratch.data(),a));
    assert(a.samples==700 && near(a.duration_s,70,0.01f) && a.seconds==70);
    assert(a.battery_s==60 && a.charging_s==10 && a.no_current_s==0 && a.source==Battery);
    assert(near(a.draw_typical_a,0.5f,0.005f) && near(a.draw_max_a,0.653f,0.005f) && a.draw_max_at_s>=20 && a.draw_max_at_s<40);
    assert(near(a.draw_min_a,0.5f,0.005f) && near(a.power_typical_w,4.1f,0.05f) && near(a.power_max_w,5.35f,0.05f));
    assert(near(a.charge_typical_a,0.4f,0.005f));
    assert(near(a.used_mah,0.5*40/3600*1000+0.65*20/3600*1000,0.2f) && near(a.charged_mah,0.4*10/3600*1000,0.1f));
    assert(near(a.v_start,8.2f,0.001f) && near(a.v_end,8.3f,0.001f) && near(a.v_min,8.2f,0.001f) && near(a.v_max,8.3f,0.001f));
    assert(near(a.battery_pct,94.4f,0.5f));
    assert(a.step_count==3);
    assert(near(a.steps[0].at_s,20,0.01f) && near(a.steps[0].from_a,0.5f,0.005f) && near(a.steps[0].to_a,0.65f,0.005f));
    assert(near(a.steps[1].at_s,40,0.01f) && near(a.steps[2].at_s,60,0.01f) && near(a.steps[2].to_a,-0.4f,0.005f));
    assert(a.change_count==2);
    assert(near(a.changes[0].at_s,20,0.01f) && a.changes[0].brightness==100 && near(a.changes[0].before_a,0.5f,0.005f) && near(a.changes[0].after_a,0.65f,0.005f));
    assert(near(a.changes[1].at_s,40,0.01f) && a.changes[1].brightness==50 && near(a.changes[1].after_a,0.5f,0.005f));
    // On USB: nothing flows.
    std::vector<Sample> u(50,Sample{8.1f,0.001f});Analysis b;
    assert(analyze(u.data(),u.size(),nullptr,0,scratch.data(),b));
    assert(b.source==NoCurrent && b.no_current_s==5 && b.battery_s==0 && b.draw_typical_a==0 && b.draw_min_a==0 && b.battery_pct<0 && b.step_count==0);
    std::vector<Sample> tiny(15,Sample{8,0.5f});
    assert(!analyze(tiny.data(),tiny.size(),nullptr,0,scratch.data(),b));
    char text[32];
    a_text(0.512f,text,sizeof(text));assert(!strcmp(text,"512 mA"));
    a_text(1.25f,text,sizeof(text));assert(!strcmp(text,"1.25 A"));
    w_text(0.42f,text,sizeof(text));assert(!strcmp(text,"420 mW"));
    w_text(4.13f,text,sizeof(text));assert(!strcmp(text,"4.1 W"));
    assert(!strcmp(source_name(NoCurrent),"no battery current"));
    assert(near(battery_percent(7.5f),50,0.01f) && battery_percent(9)==100 && battery_percent(6)==0);
    return 0;
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
