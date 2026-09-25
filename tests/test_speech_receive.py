"""Spoken-guidance receive budget (firmware/main/speech_receive.h).

The 2026-09-24 trial had 6 underruns in 76 s of speech while the Mac's TTS ran
11.5x real time and the Mac sent only 1.1-1.2x real time. The playback loop read
at most 1 KiB per 20 ms block (about 374 of the 480 frames played), so once
playing, the buffer settled near empty and any Wi-Fi pause ran it dry. This
simulates the device loop against a Wi-Fi-limited stream with pauses.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

DRIVER = r'''
#include "speech_receive.h"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
// Virtual clock in microseconds. The Mac has the whole reply ready (TTS is 11x
// real time); Wi-Fi carries `rate` bytes/s but stops for `pause_ms` every 4 s.
// Each read returns at most 1 KiB and never crosses a message, like
// esp_transport_read within one WebSocket frame.
int main(int,char** argv) {
    const unsigned limit=atoi(argv[1]);const bool old_loop=atoi(argv[2]);
    const double rate=atof(argv[3]),pause=atof(argv[4])/1000;
    const size_t message=5600,message_frames=2048,total_frames=25*24000,block=480,prebuffer=12000;
    const size_t messages=(total_frames+message_frames-1)/message_frames;
    double now=0,last_block=0,started=-1;
    size_t sent=0,in_message=0,received=0,played=0,underruns=0,max_gap_us=0,margin=total_frames;
    bool playing=false;
    // The sender stops when the device's TCP window (CONFIG_LWIP_TCP_WND_DEFAULT)
    // holds unread data, so the socket never banks more than 5,760 bytes.
    const double window=5760;double wire=0,active_before=0;
    auto active=[&]{
        const double t=now/1e6,k=std::floor(t/4);
        return t-pause*k-std::min(t-4*k,pause);
    };
    auto read=[&]()->int {
        now+=100; // per-read cost
        if(sent>=messages)return 0;
        const double consumed=static_cast<double>(sent*message+in_message);
        wire=std::min(wire+rate*(active()-active_before),consumed+window);active_before=active();
        const double waiting=wire-consumed;
        if(waiting<1)return 0;
        const size_t n=std::min({size_t(1024),message-in_message,static_cast<size_t>(waiting)});
        in_message+=n;
        if(in_message<message)return 2;
        in_message=0;++sent;received=std::min(total_frames,received+message_frames);return 1;
    };
    while(played<total_frames) {
        if(sent<messages) {
            const int result=speech_receive(read,limit);
            if(result==1 && old_loop)continue; // the old loop went straight back to reading
        }
        const size_t buffered=received-played;
        if(!playing)playing=buffered>=prebuffer || (sent>=messages && buffered);
        if(!playing){now+=1000;continue;}
        if(!buffered){++underruns;playing=false;continue;}
        if(started<0)started=now;
        if(now-started>2e6 && sent<messages)margin=std::min(margin,buffered);
        const size_t n=std::min(block,buffered);
        if(last_block>0)max_gap_us=std::max(max_gap_us,static_cast<size_t>(now-last_block));
        now+=n*1e6/24000; // the codec write blocks for the block's duration
        last_block=now;played+=n;
    }
    printf("%zu %zu %zu\n",underruns,max_gap_us,margin);
}
'''


class SpeechReceiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        root = Path(cls.directory.name)
        (root / 'driver.cpp').write_text(DRIVER)
        cls.binary = root / 'driver'
        result = subprocess.run(['clang++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                                 '-fsanitize=address,undefined', '-I', 'firmware/main',
                                 str(root / 'driver.cpp'), '-o', str(cls.binary)],
                                capture_output=True, text=True)
        assert result.returncode == 0, result.stderr

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def run_loop(self, limit, old_loop, rate, pause_ms):
        result = subprocess.run([str(self.binary), str(limit), str(int(old_loop)), str(rate), str(pause_ms)],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        underruns, max_gap_us, margin = map(int, result.stdout.split())
        return underruns, max_gap_us, margin

    def test_one_read_per_block_leaves_no_margin_for_wifi_pauses(self):
        # 190 KB/s: measured upload throughput 2026-09-25.
        _, _, margin = self.run_loop(1, True, 190_000, 0)
        self.assertLess(margin, 480)  # under one 20 ms block of cushion
        underruns, _, _ = self.run_loop(1, True, 190_000, 300)
        self.assertGreater(underruns, 0)

    def test_one_message_per_block_builds_a_cushion_without_starving_the_codec(self):
        # A 1.5 s stall needs a faster link to have banked enough; 190 KB/s was measured.
        for rate, pause_ms in ((100_000, 0), (100_000, 300), (190_000, 300), (190_000, 1500), (2_000_000, 1500)):
                with self.subTest(rate=rate, pause_ms=pause_ms):
                    underruns, max_gap_us, _ = self.run_loop(8, False, rate, pause_ms)
                    self.assertEqual(underruns, 0)
                    # Between codec writes the loop reads at most one message.
                    self.assertLess(max_gap_us, 1_000)


if __name__ == '__main__':
    unittest.main()
