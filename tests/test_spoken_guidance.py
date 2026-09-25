"""Spoken guidance (G-0002.01 Open 1): the Mac speaks the checked text; the Tab5 plays it."""
import asyncio
import base64
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from tools.investigation import ProtocolError
from tools.investigation_service import MockSession
from test_investigation import evidence, fixture


class FakeSpeaker:
    """Yields `seconds` of a 24 kHz ramp per text, in uneven chunks, recording what it read."""
    name = 'fake-tts'

    def __init__(self, seconds=1.0, fail_after=None, delay_s=0):
        self.seconds, self.fail_after, self.delay_s = seconds, fail_after, delay_s
        self.texts = []

    async def stream(self, text, stop):
        self.texts.append(text)
        total = int(self.seconds * 24000)
        sent = 0
        while sent < total:
            if stop.is_set():
                return
            if self.fail_after is not None and sent >= self.fail_after:
                raise RuntimeError('engine-secret-path')
            n = min(total - sent, 1000 + sent % 3000)
            yield b''.join((i % 2000 - 1000).to_bytes(2, 'little', signed=True) for i in range(sent, sent + n))
            sent += n
            await asyncio.sleep(self.delay_s)


class SpokenGuidanceServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.speaker = FakeSpeaker()
        await self.open(self.speaker)

    async def open(self, speaker, name='run'):
        if getattr(self, 'service', None):
            await self.service.close()
        self.sent = []
        async def send(message): self.sent.append(message)
        self.service = MockSession(self.root / name, send, speaker=speaker)
        await self.send('hello', fixture=fixture().to_dict())

    async def asyncTearDown(self):
        await self.service.close()

    async def send(self, kind, **fields):
        return await self.service.receive(dict(version=1, type=kind, boot_id='boot', session_id='session', **fields))

    async def guided(self):
        meta, raw = evidence('take-a', 1000)
        await self.send('capture_start', metadata=meta)
        for offset in range(0, len(raw), 4096):
            await self.send('capture_chunk', capture_id='take-a', offset=offset,
                            data=base64.b64encode(raw[offset:offset + 4096]).decode())
        await self.send('capture_end', capture_id='take-a', sha256=meta['sha256'])
        await self.send('turn', request_id='r1', capture_ids=['take-a'], device_ms=100, deadline_ms=15100)
        await self.service.drain()
        guidance = self.sent[-1]
        await self.send('ack', request_id='r1')
        return guidance

    def speech(self):
        return [m for m in self.sent if m['type'].startswith('speech_')]

    async def test_ready_names_the_speaker(self):
        self.assertEqual(self.sent[0]['speech_output'], 'fake-tts')
        await self.open(None, 'quiet')
        self.assertIsNone(self.sent[0]['speech_output'])

    async def test_speaks_the_checked_text_verbatim_as_a_bounded_stream(self):
        guidance = await self.guided()
        await self.send('speak', request_id='r1')
        await self.service.drain_speech()
        self.assertEqual(self.speaker.texts, [guidance['text']])
        messages = self.speech()
        self.assertEqual(messages[0], dict(version=1, type='speech_start', boot_id='boot', session_id='session',
                                           request_id='r1', format='pcm_s16le', sample_rate_hz=24000, channels=1))
        chunks = messages[1:-1]
        self.assertTrue(all(set(c) == {'version', 'type', 'boot_id', 'session_id', 'request_id', 'offset', 'data'}
                            for c in chunks))
        audio = b''.join(base64.b64decode(c['data']) for c in chunks)
        self.assertEqual([c['offset'] for c in chunks],
                         [sum(len(base64.b64decode(x['data'])) // 2 for x in chunks[:i]) for i in range(len(chunks))])
        self.assertTrue(all(len(base64.b64decode(c['data'])) <= 4096 for c in chunks))
        self.assertEqual(messages[-1], dict(version=1, type='speech_end', boot_id='boot', session_id='session',
                                            request_id='r1', status='complete', frames=24000))
        self.assertEqual(len(audio), 48000)
        # Audio is kept as evidence; the transcript logs the stream, never the samples.
        self.assertTrue((self.service.archive.root / 'speech' / 'r1.wav').exists())
        transcript = (self.service.archive.root / 'transcript.jsonl').read_text()
        self.assertNotIn(chunks[0]['data'][:64], transcript)
        record = next(json.loads(l)['message'] for l in transcript.splitlines() if '"speech_output"' in l and 'first_chunk_host_ns' in l)
        self.assertEqual((record['status'], record['frames']), ('complete', 24000))

    async def test_stop_ends_the_stream_early(self):
        await self.open(FakeSpeaker(seconds=10, delay_s=0.01), 'stop')
        await self.guided()
        await self.send('speak', request_id='r1')
        await asyncio.sleep(0.03)
        await self.send('speech_stop', request_id='r1')
        await self.service.drain_speech()
        end = self.speech()[-1]
        self.assertEqual((end['type'], end['status']), ('speech_end', 'stopped'))
        self.assertLess(end['frames'], 240000)
        self.assertEqual(sum(len(base64.b64decode(m['data'])) // 2 for m in self.speech() if m['type'] == 'speech_chunk'),
                         end['frames'])

    async def test_engine_failure_ends_the_stream_without_leaking_the_error(self):
        await self.open(FakeSpeaker(fail_after=3000), 'fail')
        await self.guided()
        await self.send('speak', request_id='r1')
        await self.service.drain_speech()
        end = self.speech()[-1]
        self.assertEqual((end['type'], end['status']), ('speech_end', 'failed'))
        self.assertNotIn('engine-secret-path', (self.service.archive.root / 'transcript.jsonl').read_text())
        # The session goes on: capture B is still accepted.
        meta, _ = evidence('take-b', 500, acquisition_start_us=30000, acquisition_end_us=50000)
        await self.send('capture_start', metadata=meta)

    async def test_speech_is_capped_at_sixty_seconds(self):
        await self.open(FakeSpeaker(seconds=61), 'long')
        await self.guided()
        await self.send('speak', request_id='r1')
        await self.service.drain_speech()
        end = self.speech()[-1]
        self.assertEqual(end['status'], 'failed')
        self.assertLessEqual(end['frames'], 60 * 24000)

    async def test_speech_rules(self):
        async def before_reply():
            await self.send('speak', request_id='r1')
        async def unknown_request():
            await self.guided(); await self.send('speak', request_id='r9')
        async def twice():
            await self.guided(); await self.send('speak', request_id='r1')
            await self.service.drain_speech(); await self.send('speak', request_id='r1')
        async def capture_while_speaking():
            await self.open(FakeSpeaker(seconds=10, delay_s=0.01), 'busy')
            await self.guided(); await self.send('speak', request_id='r1')
            meta, _ = evidence('take-b', 500, acquisition_start_us=30000, acquisition_end_us=50000)
            await self.send('capture_start', metadata=meta)
        async def stop_when_silent():
            await self.guided(); await self.send('speech_stop', request_id='r1')
        async def no_speaker():
            await self.open(None, 'none'); await self.guided(); await self.send('speak', request_id='r1')
        async def extra_field():
            await self.guided(); await self.send('speak', request_id='r1', text='say this instead')
        for name, case in [('before_reply', before_reply), ('unknown_request', unknown_request), ('twice', twice),
                           ('capture_while_speaking', capture_while_speaking), ('stop_when_silent', stop_when_silent),
                           ('no_speaker', no_speaker), ('extra_field', extra_field)]:
            with self.subTest(case=name):
                await self.open(FakeSpeaker(), name)
                with self.assertRaises(ProtocolError):
                    await case()

    async def test_comparison_can_be_spoken_after_the_session_completes(self):
        await self.guided()
        meta, raw = evidence('take-b', 500, acquisition_start_us=30000, acquisition_end_us=50000)
        await self.send('capture_start', metadata=meta)
        for offset in range(0, len(raw), 4096):
            await self.send('capture_chunk', capture_id='take-b', offset=offset,
                            data=base64.b64encode(raw[offset:offset + 4096]).decode())
        await self.send('capture_end', capture_id='take-b', sha256=meta['sha256'])
        await self.send('turn', request_id='r2', capture_ids=['take-a', 'take-b'], device_ms=100,
                        deadline_ms=15100, adjustment='Moved to B')
        await self.service.drain()
        comparison = self.sent[-1]
        await self.send('ack', request_id='r2')
        self.assertEqual(self.service.phase, 'complete')
        await self.send('speak', request_id='r2')
        await self.service.drain_speech()
        self.assertEqual(self.speaker.texts[-1], comparison['text'])
        self.assertEqual(self.speech()[-1]['status'], 'complete')

    async def test_cancel_while_speaking_stops_the_stream(self):
        await self.open(FakeSpeaker(seconds=10, delay_s=0.01), 'cancel')
        await self.guided()
        await self.send('speak', request_id='r1')
        await asyncio.sleep(0.02)
        await asyncio.wait_for(self.send('cancel'), 0.2)
        await self.service.drain_speech()
        self.assertEqual(self.service.phase, 'cancelled')
        self.assertNotIn('speech_end', [m['type'] for m in self.sent[self.sent.index(next(m for m in self.sent if m['type'] == 'cancelled')):]])


class SpeakerSeamTests(unittest.TestCase):
    def test_importing_the_seam_loads_no_model(self):
        import tools.text_to_speech as tts
        self.assertNotIn('torch', sys.modules)
        self.assertNotIn('pocket_tts', sys.modules)
        self.assertEqual(tts.DEFAULT_ENGINE, 'pocket')
        self.assertEqual(tts.POCKET_VOICE, 'alba')
        self.assertIsNone(tts.load_speaker('none'))
        with self.assertRaises(ValueError):
            tts.load_speaker('cloud')

    @unittest.skipIf(shutil.which('say') is None, 'macOS say not available')
    def test_say_fallback_streams_24k_pcm(self):
        import tools.text_to_speech as tts
        speaker = tts.load_speaker('say')
        async def collect():
            stop = asyncio.Event()
            return b''.join([chunk async for chunk in speaker.stream('Move to B.', stop)])
        audio = asyncio.run(collect())
        self.assertGreater(len(audio), 24000)  # more than half a second
        self.assertEqual(len(audio) % 2, 0)


if __name__ == '__main__':
    unittest.main()
