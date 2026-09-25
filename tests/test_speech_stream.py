"""Device-side speech stream validator (firmware/main/speech_stream.h) against real service output."""
import asyncio
import base64
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.investigation_service import MockSession
from test_investigation import evidence, fixture
from test_spoken_guidance import FakeSpeaker


DRIVER = r'''
#include "speech_stream.h"
#include <cstdio>
#include <iostream>
#include <string>
int main(){
 static int16_t buffer[48000];
 std::string line;std::getline(std::cin,line);
 const size_t capacity=std::stoul(line);
 SpeechStream stream("boot","session",buffer,capacity);
 stream.begin("r1");
 while(std::getline(std::cin,line)){
  cJSON* o=cJSON_Parse(line.c_str());
  const int result=stream.receive(o);cJSON_Delete(o);
  long long sum=0;for(size_t i=0;i<stream.frames();++i)sum=sum*31+buffer[i];
  printf("%d %zu %s %lld\n",result,stream.frames(),stream.status(),sum);
 }
}'''


def service_stream(seconds=0.5):
    """Speech messages exactly as the service emits them for request r1."""
    async def run():
        sent = []
        async def send(message): sent.append(message)
        with tempfile.TemporaryDirectory() as directory:
            service = MockSession(Path(directory), send, speaker=FakeSpeaker(seconds=seconds))
            async def message(kind, **fields):
                await service.receive(dict(version=1, type=kind, boot_id='boot', session_id='session', **fields))
            await message('hello', fixture=fixture().to_dict())
            meta, raw = evidence('take-a', 1000)
            await message('capture_start', metadata=meta)
            for offset in range(0, len(raw), 4096):
                await message('capture_chunk', capture_id='take-a', offset=offset,
                              data=base64.b64encode(raw[offset:offset + 4096]).decode())
            await message('capture_end', capture_id='take-a', sha256=meta['sha256'])
            await message('turn', request_id='r1', capture_ids=['take-a'], device_ms=100, deadline_ms=15100)
            await service.drain()
            await message('ack', request_id='r1')
            await message('speak', request_id='r1')
            await service.drain_speech()
            await service.close()
        return [m for m in sent if m['type'].startswith('speech_')]
    return asyncio.run(run())


def checksum(samples):
    total = 0
    for value in samples:
        total = (total * 31 + value) & (2**64 - 1)
    return total - 2**64 if total >= 2**63 else total


class SpeechStreamTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        root = Path(cls.temp.name)
        cjson = Path('.tools/esp-idf/components/json/cJSON')
        (root / 'driver.cpp').write_text(DRIVER)
        r = subprocess.run(['clang', '-c', '-fsanitize=address', str(cjson / 'cJSON.c'), '-o', str(root / 'cJSON.o')],
                           capture_output=True, text=True)
        if r.returncode: raise AssertionError(r.stderr)
        cls.binary = root / 'driver'
        r = subprocess.run(['clang++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-fsanitize=address',
                            '-I', 'firmware/main', '-I', str(cjson), str(root / 'driver.cpp'), str(root / 'cJSON.o'),
                            '-o', str(cls.binary)], capture_output=True, text=True)
        if r.returncode: raise AssertionError(r.stderr)
        cls.messages = service_stream()

    def run_stream(self, messages, capacity=48000):
        lines = [str(capacity)] + [m if isinstance(m, str) else json.dumps(m) for m in messages]
        r = subprocess.run([str(self.binary)], input='\n'.join(lines) + '\n', capture_output=True, text=True, timeout=10)
        self.assertEqual(r.returncode, 0, r.stderr)
        return [line.split() for line in r.stdout.splitlines()]

    def test_service_stream_decodes_to_the_same_samples(self):
        rows = self.run_stream(self.messages)
        self.assertTrue(all(row[0] == '0' for row in rows[:-1]))
        self.assertEqual(rows[-1][:3], ['1', '12000', 'complete'])
        audio = b''.join(base64.b64decode(m['data']) for m in self.messages if m['type'] == 'speech_chunk')
        samples = [int.from_bytes(audio[i:i + 2], 'little', signed=True) for i in range(0, len(audio), 2)]
        self.assertEqual(int(rows[-1][3]), checksum(samples))

    def test_stopped_and_failed_streams_end_cleanly(self):
        for status in ('stopped', 'failed'):
            with self.subTest(status=status):
                messages = copy.deepcopy(self.messages[:3])
                frames = sum(len(base64.b64decode(m['data'])) // 2 for m in messages[1:])
                messages.append({**self.messages[-1], 'status': status, 'frames': frames})
                self.assertEqual(self.run_stream(messages)[-1][:3], ['1', str(frames), status])

    def test_hostile_or_out_of_order_messages_are_rejected(self):
        start, first, second, end = self.messages[0], self.messages[1], self.messages[2], self.messages[-1]
        cases = {
            'chunk_before_start': [first],
            'wrong_request': [{**start, 'request_id': 'r2'}],
            'wrong_session': [{**start, 'session_id': 'old'}],
            'wrong_rate': [{**start, 'sample_rate_hz': 16000}],
            'extra_field': [{**start, 'volume': 11}],
            'offset_gap': [start, second],
            'odd_bytes': [start, {**first, 'data': base64.b64encode(b'abc').decode()}],
            'too_big': [start, {**first, 'data': base64.b64encode(bytes(4098)).decode()}],
            'bad_base64': [start, {**first, 'data': '@@@@'}],
            'frames_mismatch': [start, first, {**end, 'frames': 1}],
            'unknown_status': [start, first, {**end, 'status': 'partial',
                                              'frames': len(base64.b64decode(first['data'])) // 2}],
            'not_json_object': [start, '[]'],
        }
        for name, messages in cases.items():
            with self.subTest(case=name):
                self.assertEqual(self.run_stream(messages)[-1][0], '-1')
        rows = self.run_stream(self.messages[:2], capacity=100)
        self.assertEqual(rows[-1][0], '-1')  # more audio than the buffer holds
        rows = self.run_stream(self.messages + [self.messages[1]])
        self.assertEqual(rows[-1][0], '-1')  # nothing after the end


if __name__ == '__main__':
    unittest.main()
