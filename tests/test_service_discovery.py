import asyncio
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path
import unittest

from tools import service_discovery


class ServiceDiscoveryTests(unittest.TestCase):
    def test_reply_only_to_the_request(self):
        self.assertEqual(service_discovery.reply(b'TRICORDER_DISCOVER 1\n', 8765), b'TRICORDER_SERVICE 1 8765\n')
        for other in (b'', b'TRICORDER_DISCOVER 2', b'hello', b'TRICORDER_DISCOVER 1 x'):
            self.assertIsNone(service_discovery.reply(other, 8765))

    def test_responder_answers_over_udp_and_logs_once(self):
        async def run():
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
            logged = []
            transport = await service_discovery.start_responder(port, lambda ip: True,
                                                                log=lambda *a, **k: logged.append(a[0]))
            try:
                loop = asyncio.get_running_loop()
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as device:
                    device.setblocking(False)
                    for _ in range(2):
                        device.sendto(b'TRICORDER_DISCOVER 1\n', ('127.0.0.1', port))
                        answer = await asyncio.wait_for(loop.sock_recv(device, 64), 2)
                        self.assertEqual(answer, f'TRICORDER_SERVICE 1 {port}\n'.encode())
            finally:
                transport.close()
            self.assertEqual(logged, [f'Device 127.0.0.1 found this service at ws://127.0.0.1:{port}/'])
        asyncio.run(run())

    def test_device_parser_matches(self):
        compiler = shutil.which('clang++') or shutil.which('g++')
        self.assertIsNotNone(compiler)
        source = r'''
#include "service_discovery.h"
#include <cassert>
#include <initializer_list>
int main() {
    assert(discovery_reply_port("TRICORDER_SERVICE 1 8765\n")==8765);
    assert(discovery_reply_port("TRICORDER_SERVICE 1 1")==1);
    for (const char* bad : {"", "TRICORDER_SERVICE 1 ", "TRICORDER_SERVICE 1 0", "TRICORDER_SERVICE 1 65536",
                            "TRICORDER_SERVICE 1 -5", "TRICORDER_SERVICE 1 87x", "TRICORDER_SERVICE 2 8765",
                            "TRICORDER_SERVICE 1 8765\n\n", "TRICORDER_DISCOVER 1\n"})
        assert(discovery_reply_port(bad)==0);
    assert(discovery_reply_port(nullptr)==0);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path/'test.cpp').write_text(source)
            build = subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-I', 'firmware/main',
                                    str(path/'test.cpp'), '-o', str(path/'test')], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            self.assertEqual(subprocess.run([str(path/'test')]).returncode, 0)


if __name__ == '__main__':
    unittest.main()
