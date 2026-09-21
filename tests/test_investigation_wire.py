"""Transport bounds and partial-frame reassembly for the firmware LAN client."""
from pathlib import Path
import subprocess
import tempfile
import unittest

class InvestigationWireTests(unittest.TestCase):
    def test_endpoint_and_split_fragmented_frames(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);(p/'test.cpp').write_text(r'''
#include "investigation_wire.h"
#include <cassert>
#include <cstring>
int main() {
 InvestigationEndpoint e;
 assert(e.parse("ws://192.168.1.8:8765/"));assert(e.port==8765);
 assert(!strcmp(e.host,"192.168.1.8") && !strcmp(e.path,"/"));
 assert(e.parse("ws://mac.local:8765/ab"));assert(!strcmp(e.path,"/ab"));
 for(const char* s:{"wss://host/","http://host/","ws://host:0/","ws://host:65536/",
                   "ws://user:secret@host/","ws://host/path\r\nInjected: yes", "ws://", "ws://host:1x/"})assert(!e.parse(s));
 char memory[32769];InvestigationFrames f(memory);
 assert(f.append(1,7,false,"{\"a",3)==0);
 assert(f.append(1,7,false,"\": 1",4)==0);
 assert(f.append(0,1,true,"}",1)==1);assert(!strcmp(memory,"{\"a\": 1}"));
 f.reset();assert(f.append(0,1,true,"x",1)==-1);
 f.reset();assert(f.append(2,1,true,"x",1)==-1);
 f.reset();assert(f.append(1,32769,true,"x",1)==-1);
 f.reset();assert(f.append(1,2,true,"x",1)==0);
 assert(f.append(1,2,true,"y",1)==1);assert(!strcmp(memory,"xy"));
 f.reset();assert(f.append(1,2,true,"x\0",2)==-1);
 f.reset();assert(f.append(1,1,false,"x",1)==0);
 assert(f.append(1,1,true,"y",1)==-1);
 f.reset();for(int i=0;i<32768;++i)assert(f.append(1,32768,true,"x",1)==(i==32767?1:0));
 assert(strlen(memory)==32768);
}
''')
            r=subprocess.run(['clang++','-std=c++17','-Wall','-Wextra','-Werror','-fsanitize=address',
                              '-I','firmware/main',str(p/'test.cpp'),'-o',str(p/'test')],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            r=subprocess.run([str(p/'test')],capture_output=True,text=True,timeout=10)
            self.assertEqual(r.returncode,0,r.stderr)
