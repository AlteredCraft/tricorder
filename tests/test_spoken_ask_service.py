"""Spoken ask over the service: question upload, fake transcription, confirm, operator context."""
import asyncio
import base64
import json
from pathlib import Path
import tempfile
import unittest

from tools.investigation import MockProvider, ProtocolError
from tools.investigation_service import MockSession
from test_investigation import evidence, fixture
from test_question import question, speech


class FakeTranscriber:
    name = 'fake-stt'

    def __init__(self, *texts, delay_s=0):
        self.texts = list(texts)
        self.delay_s = delay_s
        self.calls = []

    async def transcribe(self, pcm):
        self.calls.append(len(pcm))
        await asyncio.sleep(self.delay_s)
        value = self.texts.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


class RecordingProvider(MockProvider):
    def __init__(self):
        self.requests = []

    def respond(self, request):
        self.requests.append(request)
        return super().respond(request)


class SpokenAskServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.transcriber = FakeTranscriber('Is the fan louder near the wall?')
        self.provider = RecordingProvider()
        await self.open(self.transcriber)

    async def open(self, transcriber, name='run', replay=False):
        self.sent = []
        async def send(message): self.sent.append(message)
        self.service = MockSession(self.root / name, send, provider=self.provider,
                                   transcriber=transcriber, replay_only=replay)
        hello = dict(fixture=fixture().to_dict())
        if replay:
            hello['replay'] = True
        await self.send('hello', **hello)

    async def asyncTearDown(self):
        await self.service.close()

    async def send(self, kind, **fields):
        return await self.service.receive(dict(version=1, type=kind, boot_id='boot',
                                               session_id='session', **fields))

    async def ask(self, key='session-q1', samples=None, **changes):
        meta, raw = question(key, samples, **changes)
        await self.send('question_start', metadata=meta)
        for offset in range(0, len(raw), 4096):
            await self.send('question_chunk', question_id=key, offset=offset,
                            data=base64.b64encode(raw[offset:offset + 4096]).decode())
        await self.send('question_end', question_id=key, sha256=meta['sha256'])
        await self.service.drain()
        return self.sent[-1]

    async def capture_a(self, key='take-a'):
        meta, raw = evidence(key, 1000)
        await self.send('capture_start', metadata=meta)
        for offset in range(0, len(raw), 4096):
            await self.send('capture_chunk', capture_id=key, offset=offset,
                            data=base64.b64encode(raw[offset:offset + 4096]).decode())
        await self.send('capture_end', capture_id=key, sha256=meta['sha256'])

    def events(self):
        path = self.service.archive.root / 'transcript.jsonl'
        return [json.loads(line)['message'] for line in path.read_text().splitlines()]

    async def test_ready_names_the_speech_to_text_engine(self):
        self.assertEqual(self.sent[0]['type'], 'ready')
        self.assertEqual(self.sent[0]['speech_to_text'], 'fake-stt')
        await self.service.close()
        await self.open(None, 'plain')
        self.assertIsNone(self.sent[0]['speech_to_text'])

    async def test_confirmed_question_becomes_operator_context_for_the_text_model(self):
        reply = await self.ask()
        self.assertEqual(set(reply), {'version', 'type', 'boot_id', 'session_id', 'question_id',
                                      'status', 'text', 'speech_to_noise_db'})
        self.assertEqual(reply['type'], 'transcript')
        self.assertEqual(reply['status'], 'heard')
        self.assertEqual(reply['text'], 'Is the fan louder near the wall?')
        self.assertAlmostEqual(reply['speech_to_noise_db'], 15, delta=1)
        self.assertEqual(self.service.phase, 'await_confirm')
        self.assertEqual(self.transcriber.calls, [96000])
        await self.send('question_confirm', question_id='session-q1', accepted=True)
        self.assertEqual(self.service.phase, 'await_a')
        await self.capture_a()
        await self.send('turn', request_id='r1', capture_ids=['take-a'], device_ms=100, deadline_ms=15100)
        await self.service.drain()
        self.assertEqual(self.sent[-1]['type'], 'guidance')
        self.assertEqual(self.provider.requests[0]['operator_question'], 'Is the fan louder near the wall?')
        run = self.service.archive.root
        # The question is its own buffer: never a measurement capture.
        self.assertEqual(sorted(p.name for p in (run / 'captures').iterdir()), ['take-a.bin', 'take-a.json'])
        self.assertTrue((run / 'questions' / 'session-q1.bin').exists())
        self.assertTrue((run / 'questions' / 'session-q1.wav').exists())
        self.assertEqual(self.service.archive.used_bytes, len(evidence()[1]))
        events = self.events()
        analysis = next(e for e in events if e.get('type') == 'question_analysis')
        self.assertEqual(analysis['transcriber'], 'fake-stt')
        self.assertAlmostEqual(analysis['speech_to_noise_db'], 15, delta=1)
        self.assertGreater(analysis['finished_host_ns'], analysis['started_host_ns'])
        self.assertTrue(any(e.get('type') == 'operator_question' and e['accepted'] for e in events))
        transcript = (run / 'transcript.jsonl').read_text()
        self.assertNotIn(base64.b64encode(question()[1][:4096]).decode(), transcript)

    async def test_transcript_is_shown_as_ascii(self):
        self.transcriber.texts = ['What\u2019s louder \u2014 the fan?']
        reply = await self.ask()
        self.assertEqual(reply['text'], "What's louder - the fan?")
        await self.send('question_confirm', question_id='session-q1', accepted=True)
        self.assertEqual(self.service.operator_question, "What's louder - the fan?")

    async def test_retry_discards_the_first_transcript(self):
        self.transcriber.texts = ['Is the van louder?', 'Is the fan louder?']
        await self.ask()
        await self.send('question_confirm', question_id='session-q1', accepted=False)
        reply = await self.ask('session-q2')
        self.assertEqual(reply['text'], 'Is the fan louder?')
        await self.send('question_confirm', question_id='session-q2', accepted=True)
        await self.capture_a()
        await self.send('turn', request_id='r1', capture_ids=['take-a'], device_ms=100, deadline_ms=15100)
        await self.service.drain()
        self.assertEqual(self.provider.requests[0]['operator_question'], 'Is the fan louder?')
        answers = [e['accepted'] for e in self.events() if e.get('type') == 'operator_question']
        self.assertEqual(answers, [False, True])

    async def test_unconfirmed_question_is_never_used(self):
        await self.ask()
        await self.send('question_confirm', question_id='session-q1', accepted=False)
        await self.capture_a()
        await self.send('turn', request_id='r1', capture_ids=['take-a'], device_ms=100, deadline_ms=15100)
        await self.service.drain()
        self.assertIsNone(self.provider.requests[0]['operator_question'])

    async def test_empty_and_failed_transcriptions_return_to_record_a(self):
        self.transcriber.texts = ['  ', RuntimeError('secret-key-in-message')]
        reply = await self.ask()
        self.assertEqual((reply['status'], reply['text']), ('empty', ''))
        self.assertEqual(self.service.phase, 'await_a')
        with self.assertRaises(ProtocolError):
            await self.send('question_confirm', question_id='session-q1', accepted=True)
        await self.open(FakeTranscriber('', RuntimeError('secret-key-in-message')), 'failed')
        await self.ask()
        reply = await self.ask('session-q2')
        self.assertEqual((reply['status'], reply['text']), ('failed', ''))
        self.assertIn('speech_to_noise_db', reply)
        self.assertNotIn('secret-key-in-message', (self.service.archive.root / 'transcript.jsonl').read_text())
        await self.capture_a()
        self.assertEqual(self.sent[-1]['stage'], 'complete')

    async def test_slow_transcription_is_bounded(self):
        await self.open(FakeTranscriber('late', delay_s=1), 'slow')
        self.service.transcribe_timeout_s = 0.05
        reply = await asyncio.wait_for(self.ask(), 0.5)
        self.assertEqual(reply['status'], 'failed')
        self.assertEqual(self.service.phase, 'await_a')

    async def test_cancel_during_transcription_discards_the_late_transcript(self):
        await self.open(FakeTranscriber('late', delay_s=5), 'cancel')
        meta, raw = question()
        await self.send('question_start', metadata=meta)
        for offset in range(0, len(raw), 4096):
            await self.send('question_chunk', question_id='session-q1', offset=offset,
                            data=base64.b64encode(raw[offset:offset + 4096]).decode())
        await self.send('question_end', question_id='session-q1', sha256=meta['sha256'])
        await asyncio.wait_for(self.send('cancel'), 0.2)
        await self.service.drain()
        self.assertEqual(self.service.phase, 'cancelled')
        self.assertFalse(any(m['type'] == 'transcript' for m in self.sent))

    async def test_questions_follow_their_own_rules(self):
        async def fresh(name, transcriber=None, replay=False):
            await self.service.close()
            await self.open(transcriber or FakeTranscriber(*['Question?'] * 6), name, replay)
        cases = []
        async def after_a():
            await self.capture_a(); await self.ask()
        cases.append(('after_capture_a', after_a))
        async def reused_id():
            await self.ask(); await self.send('question_confirm', question_id='session-q1', accepted=False)
            await self.ask()
        cases.append(('reused_id', reused_id))
        async def capture_while_confirming():
            await self.ask(); await self.capture_a()
        cases.append(('capture_while_confirming', capture_while_confirming))
        async def capture_reuses_question_id():
            await self.ask(); await self.send('question_confirm', question_id='session-q1', accepted=True)
            await self.capture_a('session-q1')
        cases.append(('capture_reuses_question_id', capture_reuses_question_id))
        async def confirm_without_transcript():
            await self.send('question_confirm', question_id='session-q1', accepted=True)
        cases.append(('confirm_without_transcript', confirm_without_transcript))
        async def confirm_wrong_id():
            await self.ask(); await self.send('question_confirm', question_id='session-q2', accepted=True)
        cases.append(('confirm_wrong_id', confirm_wrong_id))
        async def confirm_not_boolean():
            await self.ask(); await self.send('question_confirm', question_id='session-q1', accepted=1)
        cases.append(('confirm_not_boolean', confirm_not_boolean))
        async def extra_field():
            meta, _ = question()
            await self.send('question_start', metadata=meta, text='injected')
        cases.append(('extra_field', extra_field))
        async def wrong_session_metadata():
            await self.ask(session_id='other')
        cases.append(('wrong_session_metadata', wrong_session_metadata))
        async def wrong_digest():
            meta, raw = question()
            await self.send('question_start', metadata=meta)
            await self.send('question_chunk', question_id='session-q1', offset=0,
                            data=base64.b64encode(raw[:4096]).decode())
            await self.send('question_end', question_id='session-q1', sha256=meta['sha256'])
        cases.append(('short_upload', wrong_digest))
        async def too_long():
            await self.ask(samples=[0] * 128002)
        cases.append(('too_long', too_long))
        async def sixth_question():
            for n in range(1, 7):
                await self.ask(f'session-q{n}')
                await self.send('question_confirm', question_id=f'session-q{n}', accepted=False)
        cases.append(('sixth_question', sixth_question))
        for name, case in cases:
            with self.subTest(case=name):
                await fresh(name)
                with self.assertRaises(ProtocolError):
                    await case()
        await fresh('no-stt', FakeTranscriber())
        self.service.transcriber = None
        with self.assertRaises(ProtocolError):
            await self.ask()
        await fresh('replay', replay=True)
        with self.assertRaises(ProtocolError):
            await self.ask()

    async def test_five_long_questions_and_a_full_pair_fit_the_budgets(self):
        import hashlib
        await self.service.close()
        self.sent = []
        async def send(message): self.sent.append(message)
        transcriber = FakeTranscriber(*['Question?'] * 5)
        self.service = MockSession(self.root / 'full', send, transcriber=transcriber)
        f = fixture().to_dict(); f['frames'] = 144000
        await self.send('hello', fixture=f)
        long = speech(15, seconds=8.0)
        for n in range(1, 6):
            reply = await self.ask(f'session-q{n}', samples=long, stopped_by='limit')
            self.assertEqual(reply['status'], 'heard')
            await self.send('question_confirm', question_id=f'session-q{n}', accepted=n == 5)
        raw = evidence()[1][:8] * 144000
        for index in range(2):
            key = f'full-{index}'
            meta, _ = evidence(key, frames=144000, size_bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                               acquisition_start_us=100 + index * 4000000, acquisition_end_us=3000100 + index * 4000000)
            await self.send('capture_start', metadata=meta)
            for offset in range(0, len(raw), 4096):
                await self.send('capture_chunk', capture_id=key, offset=offset,
                                data=base64.b64encode(raw[offset:offset + 4096]).decode())
            await self.send('capture_end', capture_id=key, sha256=meta['sha256'])
            fields = {'adjustment': 'Moved to 40 cm'} if index else {}
            await self.send('turn', request_id=f'r{index}', capture_ids=[f'full-{i}' for i in range(index + 1)],
                            device_ms=100, deadline_ms=15100, **fields)
            await self.service.drain()
            await self.send('ack', request_id=f'r{index}')
        self.assertEqual(self.service.phase, 'complete')
        self.assertEqual(transcriber.calls, [256000] * 5)


try:
    import websockets
except ImportError:
    websockets = None


@unittest.skipIf(websockets is None, 'install tools/investigation-requirements.txt for real WebSocket tests')
class SpokenAskWebSocketTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_connection_ask_waits_for_the_operator_to_confirm(self):
        from websockets.asyncio.client import connect
        from tools.investigation_service import serve_mock
        with tempfile.TemporaryDirectory() as directory:
            server = await serve_mock('127.0.0.1', 0, Path(directory), idle_s=0.3, operator_idle_s=5,
                                      transcriber=FakeTranscriber('Is it louder?'))
            async with server:
                uri = f'ws://127.0.0.1:{server.sockets[0].getsockname()[1]}'
                async with connect(uri, proxy=None) as socket:
                    async def send(kind, **fields):
                        await socket.send(json.dumps(dict(version=1, type=kind, boot_id='boot',
                                                          session_id='session', **fields)))
                    async def receive(): return json.loads(await asyncio.wait_for(socket.recv(), 2))
                    await send('hello', fixture=fixture().to_dict())
                    self.assertEqual((await receive())['speech_to_text'], 'fake-stt')
                    meta, raw = question()
                    await send('question_start', metadata=meta)
                    for offset in range(0, len(raw), 4096):
                        await send('question_chunk', question_id='session-q1', offset=offset,
                                   data=base64.b64encode(raw[offset:offset + 4096]).decode())
                    await send('question_end', question_id='session-q1', sha256=meta['sha256'])
                    self.assertEqual((await receive())['text'], 'Is it louder?')
                    await asyncio.sleep(0.8)  # operator reading the transcript
                    await send('question_confirm', question_id='session-q1', accepted=True)
                    await asyncio.sleep(0.8)  # operator deciding to record A
                    meta, _ = evidence()
                    await send('capture_start', metadata=meta)
                    self.assertEqual((await receive())['stage'], 'start')


if __name__ == '__main__':
    unittest.main()
