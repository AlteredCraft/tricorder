"""The Mac service session: hello, voice note, Explain and the spoken reply (planning/service.md)."""
import asyncio
import base64
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from tools.service import Session, decode_message, peer_allowed, provider_settings
from tools.service_protocol import MockProvider, ProtocolError
from tools.text_to_speech import spoken_form
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


class RecordingExplainer(MockProvider):
    def __init__(self):
        self.evidence = []

    def explain(self, evidence):
        self.evidence.append(deepcopy(evidence))
        return super().explain(evidence)


def summary(**changes):
    """A sound analysis as the device sends it."""
    value = {
        'duration_s': 41.4, 'background_db': -48.4, 'loud_db': -43.8, 'average_db': -45.6,
        'max_db': -20.0, 'max_at_s': 8.5, 'threshold_db': -38.4, 'strongest_background_hz': 53.2,
        'event_count': 1,
        'events': [{'start_s': 15.3, 'duration_s': 0.34, 'peak_over_db': 11.3, 'band_hz': 6110.0,
                    'band_rise_db': 14.7}],
        'tones': [{'tone_hz': 1200.0, 'above_db': 8.1}],
        'sharp_count': 2,
        'sharp': [{'at_s': 8.5, 'peak_over_db': 28.4}, {'at_s': 30.1, 'peak_over_db': 12.0}],
        'level_max_1s': [-46.7, -43.1, -20.0, -45.2],
    }
    value.update(changes)
    return value


class SessionCase(unittest.IsolatedAsyncioTestCase):
    """One session opened with fake engines; the explain tests borrow these helpers."""
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.transcriber = FakeTranscriber('The grinder started near the end.')
        self.speaker = FakeSpeaker()
        self.provider = RecordingExplainer()
        self.service = None
        await self.open()

    async def open(self, name='run', **engines):
        if self.service:
            await self.service.close()
        self.sent = []
        async def send(message): self.sent.append(message)
        for key, value in engines.items():
            setattr(self, key, value)
        self.service = Session(self.root / name, send, provider=self.provider,
                               transcriber=self.transcriber, speaker=self.speaker)
        await self.send('hello')

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

    async def explain(self, key='explain-1', value=None):
        await self.send('analysis_explain', request_id=key, analysis=value or summary())
        await self.service.drain()
        return self.sent[-1]

    def events(self):
        path = self.service.archive.root / 'transcript.jsonl'
        return [json.loads(line)['message'] for line in path.read_text().splitlines()]


class HelloTests(SessionCase):
    async def test_ready_names_the_engines(self):
        self.assertEqual(self.sent, [dict(version=1, type='ready', boot_id='boot', session_id='session',
                                          provider='scripted-mock-v1', speech_to_text='fake-stt',
                                          speech_output='fake-tts')])
        await self.open('plain', transcriber=None, speaker=None)
        self.assertIsNone(self.sent[0]['speech_to_text'])
        self.assertIsNone(self.sent[0]['speech_output'])

    async def test_session_rules(self):
        async def duplicate_hello():
            await self.send('hello')
        async def extra_field():
            await self.open('extra-inner'); await self.service.receive(
                dict(version=1, type='speak', boot_id='boot', session_id='session', request_id='x', text='say this'))
        async def unknown_type():
            await self.send('turn', request_id='r1')
        async def wrong_version():
            await self.service.receive(dict(version=2, type='speak', boot_id='boot', session_id='session',
                                            request_id='x'))
        async def other_session():
            await self.service.receive(dict(version=1, type='analysis_explain', boot_id='boot', session_id='other',
                                            request_id='x', analysis=summary()))
        for name, case in [('duplicate_hello', duplicate_hello), ('extra_field', extra_field),
                           ('unknown_type', unknown_type), ('wrong_version', wrong_version),
                           ('other_session', other_session)]:
            with self.subTest(case=name):
                await self.open(name)
                with self.assertRaises(ProtocolError):
                    await case()

    async def test_hello_comes_first_and_a_session_directory_is_never_reused(self):
        async def send(message): pass
        fresh = Session(self.root / 'fresh', send)
        with self.assertRaises(ProtocolError):
            await fresh.receive(dict(version=1, type='speak', boot_id='boot', session_id='session', request_id='x'))
        with self.assertRaises(OSError):
            await Session(self.root / 'run', send).receive(
                dict(version=1, type='hello', boot_id='boot', session_id='session'))

    async def test_close_records_how_the_session_ended(self):
        await self.service.close()
        self.assertEqual(self.events()[-1], {'type': 'closed', 'state': 'offline', 'incomplete_questions': []})
        await self.open('explained')
        await self.explain()
        await self.service.close()
        self.assertEqual(self.events()[-1]['state'], 'complete')


class VoiceNoteTests(SessionCase):
    async def test_confirmed_note_reaches_the_text_model_as_context(self):
        reply = await self.ask()
        self.assertEqual(set(reply), {'version', 'type', 'boot_id', 'session_id', 'question_id',
                                      'status', 'text', 'speech_to_noise_db'})
        self.assertEqual((reply['type'], reply['status']), ('transcript', 'heard'))
        self.assertEqual(reply['text'], 'The grinder started near the end.')
        self.assertAlmostEqual(reply['speech_to_noise_db'], 15, delta=1)
        self.assertEqual(self.service.phase, 'await_confirm')
        self.assertEqual(self.transcriber.calls, [96000])
        await self.send('question_confirm', question_id='session-q1', accepted=True)
        self.assertEqual(self.service.phase, 'ready')
        await self.explain()
        self.assertEqual(self.provider.evidence[0]['voice_note'], 'The grinder started near the end.')
        run = self.service.archive.root
        self.assertTrue((run / 'questions' / 'session-q1.bin').exists())
        self.assertTrue((run / 'questions' / 'session-q1.wav').exists())
        events = self.events()
        analysis = next(e for e in events if e.get('type') == 'question_analysis')
        self.assertEqual(analysis['transcriber'], 'fake-stt')
        self.assertAlmostEqual(analysis['speech_to_noise_db'], 15, delta=1)
        self.assertGreater(analysis['finished_host_ns'], analysis['started_host_ns'])
        self.assertTrue(any(e.get('type') == 'operator_question' and e['accepted'] for e in events))
        transcript = (run / 'transcript.jsonl').read_text()
        self.assertNotIn(base64.b64encode(question()[1][:4096]).decode(), transcript)

    async def test_transcript_is_shown_as_ascii(self):
        self.transcriber.texts = ['What’s louder — the fan?']
        reply = await self.ask()
        self.assertEqual(reply['text'], "What's louder - the fan?")
        await self.send('question_confirm', question_id='session-q1', accepted=True)
        self.assertEqual(self.service.operator_question, "What's louder - the fan?")

    async def test_recording_again_discards_the_first_transcript(self):
        self.transcriber.texts = ['Is the van louder?', 'Is the fan louder?']
        await self.ask()
        await self.send('question_confirm', question_id='session-q1', accepted=False)
        reply = await self.ask('session-q2')
        self.assertEqual(reply['text'], 'Is the fan louder?')
        await self.send('question_confirm', question_id='session-q2', accepted=True)
        await self.explain()
        self.assertEqual(self.provider.evidence[0]['voice_note'], 'Is the fan louder?')
        answers = [e['accepted'] for e in self.events() if e.get('type') == 'operator_question']
        self.assertEqual(answers, [False, True])

    async def test_unconfirmed_note_is_never_used(self):
        await self.ask()
        await self.send('question_confirm', question_id='session-q1', accepted=False)
        await self.explain()
        self.assertIsNone(self.provider.evidence[0]['voice_note'])

    async def test_empty_and_failed_transcriptions_need_no_confirmation(self):
        self.transcriber.texts = ['  ', RuntimeError('secret-key-in-message')]
        reply = await self.ask()
        self.assertEqual((reply['status'], reply['text']), ('empty', ''))
        self.assertEqual(self.service.phase, 'ready')
        with self.assertRaises(ProtocolError):
            await self.send('question_confirm', question_id='session-q1', accepted=True)
        await self.open('failed', transcriber=FakeTranscriber('', RuntimeError('secret-key-in-message')))
        await self.ask()
        reply = await self.ask('session-q2')
        self.assertEqual((reply['status'], reply['text']), ('failed', ''))
        self.assertIn('speech_to_noise_db', reply)
        self.assertNotIn('secret-key-in-message', (self.service.archive.root / 'transcript.jsonl').read_text())
        self.assertEqual((await self.explain())['type'], 'analysis_reply')

    async def test_slow_transcription_is_bounded(self):
        await self.open('slow', transcriber=FakeTranscriber('late', delay_s=1))
        self.service.transcribe_timeout_s = 0.05
        reply = await asyncio.wait_for(self.ask(), 0.5)
        self.assertEqual(reply['status'], 'failed')
        self.assertEqual(self.service.phase, 'ready')

    async def test_voice_note_rules(self):
        async def after_the_explain():
            await self.explain(); await self.ask()
        async def reused_id():
            await self.ask(); await self.send('question_confirm', question_id='session-q1', accepted=False)
            await self.ask()
        async def explain_while_confirming():
            await self.ask(); await self.explain()
        async def confirm_without_transcript():
            await self.send('question_confirm', question_id='session-q1', accepted=True)
        async def confirm_wrong_id():
            await self.ask(); await self.send('question_confirm', question_id='session-q2', accepted=True)
        async def confirm_not_boolean():
            await self.ask(); await self.send('question_confirm', question_id='session-q1', accepted=1)
        async def extra_field():
            meta, _ = question()
            await self.send('question_start', metadata=meta, text='injected')
        async def wrong_session_metadata():
            await self.ask(session_id='other')
        async def short_upload():
            meta, raw = question()
            await self.send('question_start', metadata=meta)
            await self.send('question_chunk', question_id='session-q1', offset=0,
                            data=base64.b64encode(raw[:4096]).decode())
            await self.send('question_end', question_id='session-q1', sha256=meta['sha256'])
        async def too_long():
            await self.ask(samples=[0] * 128002)
        async def sixth_note():
            for n in range(1, 7):
                await self.ask(f'session-q{n}')
                await self.send('question_confirm', question_id=f'session-q{n}', accepted=False)
        async def no_speech_to_text():
            self.service.transcriber = None
            await self.ask()
        cases = [after_the_explain, reused_id, explain_while_confirming, confirm_without_transcript,
                 confirm_wrong_id, confirm_not_boolean, extra_field, wrong_session_metadata, short_upload,
                 too_long, sixth_note, no_speech_to_text]
        for case in cases:
            with self.subTest(case=case.__name__):
                await self.open(case.__name__, transcriber=FakeTranscriber(*['Question?'] * 6))
                with self.assertRaises(ProtocolError):
                    await case()

    async def test_five_full_length_notes_fit_the_budget(self):
        transcriber = FakeTranscriber(*['Question?'] * 5)
        await self.open('full', transcriber=transcriber)
        long = speech(15, seconds=8.0)
        for n in range(1, 6):
            reply = await self.ask(f'session-q{n}', samples=long, stopped_by='limit')
            self.assertEqual(reply['status'], 'heard')
            await self.send('question_confirm', question_id=f'session-q{n}', accepted=n == 5)
        self.assertEqual((await self.explain())['type'], 'analysis_reply')
        self.assertEqual(transcriber.calls, [256000] * 5)


class SpokenReplyTests(SessionCase):
    def speech(self):
        return [m for m in self.sent if m['type'].startswith('speech_')]

    async def test_speaks_the_checked_text_as_a_bounded_stream(self):
        reply = await self.explain()
        await self.send('speak', request_id='explain-1')
        await self.service.drain_speech()
        self.assertEqual(self.speaker.texts, [spoken_form(reply['text'])])
        messages = self.speech()
        self.assertEqual(messages[0], dict(version=1, type='speech_start', boot_id='boot', session_id='session',
                                           request_id='explain-1', format='pcm_s16le', sample_rate_hz=24000,
                                           channels=1))
        chunks = messages[1:-1]
        self.assertTrue(all(set(c) == {'version', 'type', 'boot_id', 'session_id', 'request_id', 'offset', 'data'}
                            for c in chunks))
        audio = b''.join(base64.b64decode(c['data']) for c in chunks)
        self.assertEqual([c['offset'] for c in chunks],
                         [sum(len(base64.b64decode(x['data'])) // 2 for x in chunks[:i]) for i in range(len(chunks))])
        self.assertTrue(all(len(base64.b64decode(c['data'])) <= 4096 for c in chunks))
        self.assertEqual(messages[-1], dict(version=1, type='speech_end', boot_id='boot', session_id='session',
                                            request_id='explain-1', status='complete', frames=24000))
        self.assertEqual(len(audio), 48000)
        # The audio is saved; the transcript logs the stream, never the samples.
        self.assertTrue((self.service.archive.root / 'speech' / 'explain-1.wav').exists())
        transcript = (self.service.archive.root / 'transcript.jsonl').read_text()
        self.assertNotIn(chunks[0]['data'][:64], transcript)
        record = next(e for e in self.events() if e.get('type') == 'speech_output')
        self.assertEqual((record['status'], record['frames']), ('complete', 24000))

    async def test_stop_ends_the_stream_early(self):
        await self.open('stop', speaker=FakeSpeaker(seconds=10, delay_s=0.01))
        await self.explain()
        await self.send('speak', request_id='explain-1')
        await asyncio.sleep(0.03)
        await self.send('speech_stop', request_id='explain-1')
        await self.service.drain_speech()
        end = self.speech()[-1]
        self.assertEqual((end['type'], end['status']), ('speech_end', 'stopped'))
        self.assertLess(end['frames'], 240000)
        self.assertEqual(sum(len(base64.b64decode(m['data'])) // 2 for m in self.speech() if m['type'] == 'speech_chunk'),
                         end['frames'])
        # A stop that crosses the end already in flight is harmless.
        await self.send('speech_stop', request_id='explain-1')

    async def test_engine_failure_ends_the_stream_without_leaking_the_error(self):
        await self.open('fail', speaker=FakeSpeaker(fail_after=3000))
        await self.explain()
        await self.send('speak', request_id='explain-1')
        await self.service.drain_speech()
        end = self.speech()[-1]
        self.assertEqual((end['type'], end['status']), ('speech_end', 'failed'))
        self.assertNotIn('engine-secret-path', (self.service.archive.root / 'transcript.jsonl').read_text())

    async def test_speech_is_capped_at_sixty_seconds(self):
        await self.open('long', speaker=FakeSpeaker(seconds=61))
        await self.explain()
        await self.send('speak', request_id='explain-1')
        await self.service.drain_speech()
        end = self.speech()[-1]
        self.assertEqual(end['status'], 'failed')
        self.assertLessEqual(end['frames'], 60 * 24000)

    async def test_speech_rules(self):
        async def before_the_reply():
            await self.send('speak', request_id='explain-1')
        async def unknown_request():
            await self.explain(); await self.send('speak', request_id='explain-9')
        async def twice():
            await self.explain(); await self.send('speak', request_id='explain-1')
            await self.service.drain_speech(); await self.send('speak', request_id='explain-1')
        async def another_message_while_speaking():
            await self.open('busy', speaker=FakeSpeaker(seconds=10, delay_s=0.01))
            await self.explain(); await self.send('speak', request_id='explain-1')
            await self.send('analysis_explain', request_id='explain-2', analysis=summary())
        async def stop_when_silent():
            await self.explain(); await self.send('speech_stop', request_id='explain-1')
        async def no_speaker():
            await self.open('none', speaker=None); await self.explain()
            await self.send('speak', request_id='explain-1')
        async def extra_field():
            await self.explain(); await self.send('speak', request_id='explain-1', text='say this instead')
        for case in [before_the_reply, unknown_request, twice, another_message_while_speaking, stop_when_silent,
                     no_speaker, extra_field]:
            with self.subTest(case=case.__name__):
                await self.open(case.__name__, speaker=FakeSpeaker())
                with self.assertRaises(ProtocolError):
                    await case()


class WireTests(unittest.TestCase):
    def test_reject_duplicate_keys_nan_binary_and_oversized_messages(self):
        for wire in ('{"type":"a","type":"b"}', '{"x":NaN}', '[]', b'{}', ' ' * 32769):
            with self.subTest(wire=repr(wire[:50])), self.assertRaises(ProtocolError):
                decode_message(wire)


class PeerPolicyTests(unittest.TestCase):
    def test_only_private_or_loopback_peers_may_connect(self):
        for address in ('127.0.0.1', '::1', '192.168.4.2', '172.20.10.9', '10.0.0.5', 'fd00::1'):
            self.assertTrue(peer_allowed(address), address)
        for address in ('8.8.8.8', '2001:4860:4860::8888', '93.184.216.34', 'not-an-address', None):
            self.assertFalse(peer_allowed(address), address)


class ProviderSettingsTests(unittest.TestCase):
    def test_local_server_needs_no_key_and_allows_a_slow_model(self):
        local = provider_settings('local')
        self.assertEqual((local['base_url'], local['model'], local['needs_key']),
                         ('http://127.0.0.1:11434/v1', 'gemma4:latest', False))
        self.assertGreaterEqual(local['timeout_s'], 30)
        custom = provider_settings('local', model='llama3.2:3b', base_url='http://127.0.0.1:1234/v1')
        self.assertEqual((custom['base_url'], custom['model']), ('http://127.0.0.1:1234/v1', 'llama3.2:3b'))
        router = provider_settings('openrouter')
        self.assertEqual((router['base_url'], router['model'], router['needs_key']),
                         ('https://openrouter.ai/api/v1', 'openai/gpt-5.6-sol', True))
        self.assertEqual(provider_settings('openai')['model'], 'gpt-4.1-mini')
        with self.assertRaises(ValueError):
            provider_settings('mock')
        with self.assertRaises(ValueError):
            provider_settings('openrouter', base_url='http://127.0.0.1:1/v1')


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
            return b''.join([chunk async for chunk in speaker.stream('Move the device.', stop)])
        audio = asyncio.run(collect())
        self.assertGreater(len(audio), 24000)  # more than half a second
        self.assertEqual(len(audio) % 2, 0)


try:
    import websockets
except ImportError:
    websockets = None


@unittest.skipIf(websockets is None, 'install tools/investigation-requirements.txt for real WebSocket tests')
class WebSocketTests(unittest.IsolatedAsyncioTestCase):
    async def serve(self, directory, **options):
        from tools.service import serve_sessions
        server = await serve_sessions('127.0.0.1', 0, Path(directory), **options)
        return server, f'ws://127.0.0.1:{server.sockets[0].getsockname()[1]}'

    @staticmethod
    def wire(kind, **fields):
        return json.dumps(dict(version=1, type=kind, boot_id='boot', session_id='session', **fields))

    async def test_explain_and_spoken_reply_over_a_real_connection(self):
        from websockets.asyncio.client import connect
        with tempfile.TemporaryDirectory() as directory:
            server, uri = await self.serve(directory, speaker=FakeSpeaker(seconds=0.2))
            async with server:
                async with connect(uri, proxy=None) as socket:
                    async def receive(): return json.loads(await asyncio.wait_for(socket.recv(), 2))
                    await socket.send(self.wire('hello'))
                    self.assertEqual((await receive())['type'], 'ready')
                    # One device at a time.
                    async with connect(uri, proxy=None) as second:
                        with self.assertRaises(websockets.exceptions.ConnectionClosed):
                            await second.recv()
                    await socket.send(self.wire('analysis_explain', request_id='explain-1', analysis=summary()))
                    reply = await receive()
                    self.assertEqual((reply['type'], reply['request_id']), ('analysis_reply', 'explain-1'))
                    await socket.send(self.wire('speak', request_id='explain-1'))
                    kinds = []
                    while not kinds or kinds[-1] != 'speech_end':
                        kinds.append((await receive())['type'])
                    self.assertEqual((kinds[0], set(kinds[1:-1])), ('speech_start', {'speech_chunk'}))

    async def test_transport_close_records_codes_without_peer_reason(self):
        from websockets.asyncio.client import connect
        with tempfile.TemporaryDirectory() as directory:
            server, uri = await self.serve(directory)
            async with server:
                async with connect(uri, proxy=None) as socket:
                    await socket.send(self.wire('hello'))
                    await socket.recv()
                    await socket.close(code=1000, reason='private-peer-reason')
            transcript = (Path(directory) / 'boot-session/transcript.jsonl').read_text()
            self.assertNotIn('private-peer-reason', transcript)
            events = [json.loads(line)['message'] for line in transcript.splitlines()]
            closure = next(event for event in events if event.get('type') == 'transport_closed')
            self.assertEqual((closure['received_code'], closure['sent_code']), (1000, 1000))

    async def test_reading_a_transcript_outlasts_the_message_idle_limit(self):
        # The person reads the transcript for longer than a message gap; a stalled upload
        # still hits the short limit. Ping/pong detects a dead device either way.
        from websockets.asyncio.client import connect
        with tempfile.TemporaryDirectory() as directory:
            server, uri = await self.serve(directory, idle_s=0.3, operator_idle_s=5,
                                           transcriber=FakeTranscriber('Is it louder?', 'Again?'))
            async with server:
                async with connect(uri, proxy=None) as socket:
                    async def receive(): return json.loads(await asyncio.wait_for(socket.recv(), 2))
                    await socket.send(self.wire('hello'))
                    self.assertEqual((await receive())['speech_to_text'], 'fake-stt')
                    meta, raw = question()
                    await socket.send(self.wire('question_start', metadata=meta))
                    for offset in range(0, len(raw), 4096):
                        await socket.send(self.wire('question_chunk', question_id='session-q1', offset=offset,
                                                    data=base64.b64encode(raw[offset:offset + 4096]).decode()))
                    await socket.send(self.wire('question_end', question_id='session-q1', sha256=meta['sha256']))
                    self.assertEqual((await receive())['text'], 'Is it louder?')
                    await asyncio.sleep(0.8)  # reading the transcript
                    await socket.send(self.wire('question_confirm', question_id='session-q1', accepted=False))
                    meta, _ = question('session-q2')
                    await socket.send(self.wire('question_start', metadata=meta))
                    await asyncio.sleep(0.8)  # stalled mid-upload
                    with self.assertRaises(websockets.exceptions.ConnectionClosed):
                        await receive()
            transcript = (Path(directory) / 'boot-session/transcript.jsonl').read_text()
            self.assertIn('"state": "incomplete"', transcript)


if __name__ == '__main__':
    unittest.main()
