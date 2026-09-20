"""Copied camera frames cannot be replaced while a consumer owns them."""
from pathlib import Path
import tempfile,subprocess,unittest
class OwnedFrameTests(unittest.TestCase):
    def test_exclusive_copy_and_cross_thread_lifetime(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);(p/'test.cpp').write_text(r'''
#include "owned_frame.h"
#include <thread>
#include <cassert>
#include <cstring>
int main() {
 unsigned char memory[1024],source[1024];OwnedFrame slot(memory,sizeof(memory));
 FrameStamp stamp{};stamp.sequence=1;
 assert(!slot.copy(source,1023,stamp));
 memset(source,23,sizeof(source));assert(slot.copy(source,sizeof(source),stamp));
 assert(!slot.copy(source,sizeof(source),stamp));
 const unsigned char* held=nullptr;FrameStamp actual;
 assert(slot.acquire(held,actual) && actual.sequence==1);
 memset(source,77,sizeof(source));assert(held[0]==23 && held[1023]==23);
 assert(!slot.copy(source,sizeof(source),stamp));assert(!slot.acquire(held,actual));slot.release();
 std::thread consumer([&]{for (unsigned n=1;n<=10000;++n) {
  while(!slot.acquire(held,actual)) std::this_thread::yield();
  assert(actual.sequence==n);
  for (unsigned i=0;i<1024;++i) assert(held[i]==static_cast<unsigned char>(n));
  slot.release();
 }});
 for (unsigned n=1;n<=10000;++n) {memset(source,n,sizeof(source));stamp.sequence=n;
  while(!slot.copy(source,sizeof(source),stamp)) std::this_thread::yield();
  memset(source,0,sizeof(source));
 }
 consumer.join();assert(slot.idle());
}
''')
            subprocess.run(['clang++','-std=c++17','-pthread','-Wall','-Wextra','-Werror','-I','firmware/main',str(p/'test.cpp'),'-o',str(p/'test')],check=True,capture_output=True)
            subprocess.run([str(p/'test')],check=True)
