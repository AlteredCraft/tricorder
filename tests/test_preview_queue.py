"""Preview replacement must never change a renderer-held frame."""
from pathlib import Path
import subprocess
import tempfile
import unittest


class PreviewQueueTests(unittest.TestCase):
    def test_latest_pending_immutable_display_and_threaded_accounting(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);(p/'test.cpp').write_text(r'''
#include "preview_queue.h"
#include <thread>
#include <cassert>
#include <cstring>
int main() {
 PreviewQueue q;unsigned char memory[3][64]{};
 auto publish=[&](unsigned n) {int i=q.begin_write();assert(i>=0);
  memset(memory[i],n,64);q.publish(i,n);};
 publish(1);int displayed=q.take_latest();assert(displayed>=0 && q.generation(displayed)==1);
 for(unsigned n=2;n<=100;++n) {publish(n);assert(memory[displayed][0]==1);}
 int latest=q.take_latest();assert(q.generation(latest)==100 && memory[latest][0]==100);
 assert(q.produced()==100 && q.selected()==2 && q.replaced()==98 && q.pending()==0);
 assert(q.take_latest()==-1);q.release_display();
 int abandoned=q.begin_write();assert(abandoned>=0);q.cancel_write(abandoned);
 // Separate producer/renderer run. The selected buffer stays immutable while
 // the producer repeatedly replaces the single pending item.
 PreviewQueue threaded;std::atomic<bool> done{false};unsigned seen=0;
 std::thread render([&]{unsigned previous=0;
  while (!done.load() || threaded.pending()) {
   int i=threaded.take_latest();if(i<0) {std::this_thread::yield();continue;}
   unsigned n=threaded.generation(i);assert(n>previous);previous=n;++seen;
   for(unsigned repeat=0;repeat<20;++repeat) {
    for(unsigned b=0;b<64;++b) assert(memory[i][b]==static_cast<unsigned char>(n));
    std::this_thread::yield();
   }
  }
  assert(previous==10000);threaded.release_display();
 });
 for(unsigned n=1;n<=10000;++n) {
  int i;while((i=threaded.begin_write())<0) std::this_thread::yield();
  memset(memory[i],n,64);threaded.publish(i,n);
 }
 done.store(true);render.join();
 assert(threaded.produced()==10000 && threaded.selected()==seen);
 assert(threaded.produced()==threaded.replaced()+threaded.selected());
 // Exact packed RGB565 2x nearest-neighbor selection; never modify source.
 uint16_t source[8*6],output[4*3];for(unsigned i=0;i<48;++i)source[i]=i;
 assert(preview_half_rgb565(source,sizeof(source),8,6,output,sizeof(output)));
 for(unsigned y=0;y<3;++y)for(unsigned x=0;x<4;++x)assert(output[y*4+x]==source[y*16+x*2]);
 for(unsigned i=0;i<48;++i)assert(source[i]==i);
 assert(!preview_half_rgb565(source,sizeof(source)-2,8,6,output,sizeof(output)));
 assert(!preview_half_rgb565(source,sizeof(source),7,6,output,sizeof(output)));
 assert(!preview_half_rgb565(source,sizeof(source),8,6,output,sizeof(output)-2));
 assert(!preview_half_rgb565(nullptr,sizeof(source),8,6,output,sizeof(output)));
}
''')
            result=subprocess.run(['clang++','-std=c++17','-O2','-pthread','-fsanitize=address',
                                   '-Wall','-Wextra','-Werror','-I','firmware/main',str(p/'test.cpp'),
                                   '-o',str(p/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(p/'test')],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
