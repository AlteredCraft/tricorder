"""Exercise bounded TCP completion below WebSocket framing with short writes."""
from pathlib import Path
import subprocess
import tempfile
import unittest


class TransportWriteTests(unittest.TestCase):
    def test_partial_writes_deadline_cancel_and_no_progress(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'test.cpp'
            source.write_text(r'''
#include "transport_write.h"
#include <cassert>
#include <string>
#include <vector>
int main() {
    std::string input;
    for(int i=0;i<22000;++i)input.push_back(static_cast<char>(i%251));
    std::string received;
    uint64_t now=100;
    bool cancelled=false;
    std::vector<int> budgets;
    auto clock=[&](){return now;};
    auto cancel=[&](){return cancelled;};
    auto partial=[&](const char* p,int n,int budget){
        budgets.push_back(budget); now+=5;
        int count=n>731?731:n; received.append(p,count); return count;
    };
    assert(transport_write_all(input.data(),input.size(),2000,partial,clock,cancel)==22000);
    assert(received==input && budgets.size()>1);
    assert(budgets.back()<budgets.front());
    int calls=0; now=0;
    auto stalls=[&](const char*,int,int budget){++calls;now+=budget;return 0;};
    assert(transport_write_all(input.data(),input.size(),20,stalls,clock,cancel)==-1);
    assert(calls==1);
    calls=0;now=0;
    auto slow=[&](const char*,int,int){++calls;now+=10;return 1;};
    assert(transport_write_all(input.data(),input.size(),20,slow,clock,cancel)==-1);
    assert(calls==2); // one total deadline, never 20 ms per retry
    calls=0;now=0;
    auto stop=[&](const char*,int,int){++calls;cancelled=true;return 1;};
    assert(transport_write_all(input.data(),input.size(),20,stop,clock,cancel)==-1);
    assert(calls==1);
    cancelled=false;calls=0;now=0;
    auto bad=[&](const char*,int,int){++calls;return -1;};
    assert(transport_write_all(input.data(),input.size(),20,bad,clock,cancel)==-1);
    assert(calls==1);
    auto oversized=[](const char*,int n,int){return n+1;};
    assert(transport_write_all(input.data(),input.size(),20,oversized,clock,cancel)==-1);
    assert(transport_write_all(input.data(),input.size(),0,partial,clock,cancel)==-1);
}
''')
            result = subprocess.run([
                'clang++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined', '-I', 'firmware/main',
                str(source), '-o', str(root / 'test')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(root / 'test')], capture_output=True,
                                    text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
