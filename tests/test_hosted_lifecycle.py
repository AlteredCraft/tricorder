from pathlib import Path
import subprocess
import tempfile
import unittest


class HostedLifecycleTests(unittest.TestCase):
    def test_constructor_defers_and_running_scheduler_propagates_result(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            (temporary/'freertos').mkdir()
            (temporary/'esp_err.h').write_text('typedef int esp_err_t;\n#define ESP_OK 0\n')
            (temporary/'freertos/FreeRTOS.h').write_text('#define taskSCHEDULER_NOT_STARTED 0\n')
            (temporary/'freertos/task.h').write_text('extern "C" int xTaskGetSchedulerState();\n')
            source = temporary/'test.cpp'
            source.write_text('''
#include <cassert>
extern "C" int __wrap_esp_hosted_init();
int state=0, calls=0, result=0;
extern "C" int xTaskGetSchedulerState() { return state; }
extern "C" int __real_esp_hosted_init() { ++calls; return result; }
int main() {
    assert(__wrap_esp_hosted_init()==0 && calls==0);
    state=1;
    assert(__wrap_esp_hosted_init()==0 && calls==1);
    result=-9;
    assert(__wrap_esp_hosted_init()==-9 && calls==2);
}
''')
            subprocess.run(['clang++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                            '-I', str(temporary), str(source),
                            str(root/'firmware/main/hosted_lifecycle.cpp'),
                            '-o', str(temporary/'test')], check=True, capture_output=True)
            subprocess.run([str(temporary/'test')], check=True)
