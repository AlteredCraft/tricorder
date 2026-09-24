"""Operator-owned A/B with a repeat of A (G-0002.01 revision 2026-09-24).

A is where the person is; the guidance names B; the person returns to A and
records it again so the comparison reports the A-to-A change next to B/A.
"""
import base64
import copy
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest

from tools.investigation import (Fixture, Investigation, MockProvider, ProtocolError, comparison,
                                 validate_reply, validate_request)
from tools.investigation_service import MockSession
from test_investigation import captured, evidence, fixture

A_TO_B = dict(acquisition_start_us=30000, acquisition_end_us=50000)
REPEAT = dict(acquisition_start_us=60000, acquisition_end_us=80000)


def repeat_flow(repeat_amplitude=900):
    flow = Investigation('boot', 'session', fixture(), repeat=True)
    flow.ask(); flow.start_capture()
    flow.accept(MockProvider().respond(flow.finish_capture(captured())))
    flow.adjust('Moved to B as the guidance described')
    flow.start_capture()
    return flow, captured('take-b', 500, **A_TO_B), captured('take-r', repeat_amplitude, **REPEAT)


class RepeatReferenceTests(unittest.TestCase):
    def test_return_to_a_then_compare_all_three(self):
        flow, b, r = repeat_flow()
        self.assertIsNone(flow.finish_capture(b))
        self.assertEqual(flow.state, 'return_a')
        flow.start_capture()
        self.assertEqual(flow.state, 'recording_repeat')
        request = flow.finish_capture(r)
        self.assertEqual([c['capture_id'] for c in request['captures']], ['take-a', 'take-b', 'take-r'])
        reply = MockProvider().respond(request)
        self.assertAlmostEqual(reply['comparison']['rms_delta_db'], 20 * math.log10(500 / 1000))
        self.assertAlmostEqual(reply['comparison']['repeat_delta_db'], 20 * math.log10(900 / 1000))
        self.assertIn('repeat', reply['text'].lower())
        flow.accept(reply)
        self.assertEqual([t['state'] for t in flow.transitions][-5:],
                         ['recording_b', 'return_a', 'recording_repeat', 'waiting', 'complete'])

    def test_pair_comparison_has_no_repeat_value(self):
        flow = Investigation('boot', 'session', fixture())
        flow.ask(); flow.start_capture()
        flow.accept(MockProvider().respond(flow.finish_capture(captured())))
        flow.adjust('Moved to B'); flow.start_capture()
        reply = MockProvider().respond(flow.finish_capture(captured('take-b', 500, **A_TO_B)))
        self.assertIsNone(reply['comparison']['repeat_delta_db'])
        self.assertEqual(set(reply['comparison']), {'rms_delta_db', 'repeat_delta_db', 'status', 'unit'})

    def test_clipped_or_silent_repeat_makes_the_comparison_inconclusive(self):
        for amplitude in (32767, 0):
            with self.subTest(amplitude=amplitude):
                flow, b, r = repeat_flow(amplitude)
                flow.finish_capture(b); flow.start_capture()
                result = MockProvider().respond(flow.finish_capture(r))['comparison']
                self.assertEqual(result['status'], 'inconclusive')
                self.assertIsNone(result['rms_delta_db'])
                self.assertIsNone(result['repeat_delta_db'])

    def test_repeat_must_follow_b_and_be_a_new_capture(self):
        for change in ({'capture_id': 'take-a'}, {'capture_id': 'take-b'},
                       {'acquisition_start_us': 49999}, {'gain_db': 30}):
            with self.subTest(change=change):
                flow, b, _ = repeat_flow()
                flow.finish_capture(b); flow.start_capture()
                with self.assertRaises(ProtocolError):
                    flow.finish_capture(captured('take-r', 900, **{**REPEAT, **change}))
        flow, b, r = repeat_flow()
        flow.finish_capture(b); flow.start_capture(); flow.finish_capture(r)
        with self.assertRaises(ProtocolError):
            flow.start_capture()

    def test_request_capture_counts_and_order(self):
        flow, b, r = repeat_flow()
        flow.finish_capture(b); flow.start_capture()
        request = flow.finish_capture(r)
        validate_request(request)
        for bad in (request['captures'] + [request['captures'][0]], request['captures'][:1]):
            with self.subTest(count=len(bad)), self.assertRaises(ProtocolError):
                validate_request({**request, 'captures': bad})
        swapped = copy.deepcopy(request)
        swapped['captures'][1], swapped['captures'][2] = swapped['captures'][2], swapped['captures'][1]
        with self.assertRaises(ProtocolError):
            validate_request(swapped)
        reply = MockProvider().respond(request)
        bad = copy.deepcopy(reply); bad['comparison']['repeat_delta_db'] = 0.0
        with self.assertRaises(ProtocolError):
            validate_reply(request, bad)

    def test_comparison_values_are_host_computed(self):
        items = [captured().to_dict(), captured('take-b', 500, **A_TO_B).to_dict(),
                 captured('take-r', 2000, **REPEAT).to_dict()]
        result = comparison(items)
        self.assertAlmostEqual(result['repeat_delta_db'], 20 * math.log10(2))

    def test_generic_fixture_keeps_settings_and_drops_the_tone_script(self):
        path = Path('planning/fixtures/G-0002.01-open-ab.json')
        generic = Fixture(**json.loads(path.read_text()))
        self.assertEqual((generic.frames, generic.gain_db, generic.source_slot), (144000, 24, 0))
        text = ' '.join([generic.question, generic.variable, generic.placement_a, generic.placement_b])
        self.assertNotIn('inches', text)
        self.assertNotIn('1000 Hz', text)
        cmake = Path('firmware/main/CMakeLists.txt').read_text()
        self.assertIn('G-0002.01-open-ab.json', cmake)


class RepeatServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.sent = []
        async def send(message): self.sent.append(message)
        self.service = MockSession(self.root, send)
        await self.send('hello', fixture=fixture().to_dict())

    async def asyncTearDown(self):
        await self.service.close()

    async def send(self, kind, **fields):
        return await self.service.receive(dict(version=1, type=kind, boot_id='boot', session_id='session', **fields))

    async def capture(self, key, amplitude, **fields):
        meta, raw = evidence(key, amplitude, **fields)
        await self.send('capture_start', metadata=meta)
        for offset in range(0, len(raw), 4096):
            await self.send('capture_chunk', capture_id=key, offset=offset,
                            data=base64.b64encode(raw[offset:offset + 4096]).decode())
        await self.send('capture_end', capture_id=key, sha256=meta['sha256'])

    async def turn(self, request_id, ids, **fields):
        await self.send('turn', request_id=request_id, capture_ids=ids, device_ms=100, deadline_ms=15100, **fields)
        await self.service.drain()
        return self.sent[-1]

    async def a_then_b(self):
        await self.capture('take-a', 1000)
        await self.turn('r1', ['take-a'])
        await self.send('ack', request_id='r1')
        await self.capture('take-b', 500, **A_TO_B)

    async def test_repeat_of_a_joins_the_comparison(self):
        await self.a_then_b()
        self.assertEqual(self.service.phase, 'compare_ready')
        await self.capture('take-r', 900, **REPEAT)
        reply = await self.turn('r2', ['take-a', 'take-b', 'take-r'], adjustment='Moved to B as guided')
        self.assertAlmostEqual(reply['comparison']['repeat_delta_db'], 20 * math.log10(0.9))
        self.assertAlmostEqual(reply['comparison']['rms_delta_db'], 20 * math.log10(0.5))
        await self.send('ack', request_id='r2')
        self.assertEqual(self.service.phase, 'complete')
        self.assertEqual(len(list((self.service.archive.root / 'captures').glob('*.bin'))), 3)

    async def test_pair_without_repeat_still_compares(self):
        await self.a_then_b()
        reply = await self.turn('r2', ['take-a', 'take-b'], adjustment='Moved to B')
        self.assertIsNone(reply['comparison']['repeat_delta_db'])

    async def test_repeat_rules(self):
        cases = {
            'turn_omits_uploaded_repeat': lambda: self.turn('r2', ['take-a', 'take-b'], adjustment='B'),
            'fourth_capture': lambda: self.capture('take-x', 700, acquisition_start_us=90000, acquisition_end_us=99000),
            'overlaps_b': None,
        }
        for name in cases:
            with self.subTest(case=name):
                await self.service.close()
                async def send(message): self.sent.append(message)
                self.service = MockSession(self.root / name, send)
                await self.send('hello', fixture=fixture().to_dict())
                await self.a_then_b()
                with self.assertRaises(ProtocolError):
                    if name == 'overlaps_b':
                        await self.capture('take-r', 900, acquisition_start_us=49000, acquisition_end_us=70000)
                    else:
                        await self.capture('take-r', 900, **REPEAT)
                        await cases[name]()

    async def test_three_full_captures_fit_the_wire_and_archive_budgets(self):
        await self.service.close()
        async def send(message): self.sent.append(message)
        self.service = MockSession(self.root / 'full', send)
        f = fixture().to_dict(); f['frames'] = 144000
        await self.send('hello', fixture=f)
        raw = evidence()[1][:8] * 144000
        keys = []
        for index in range(3):
            key = f'full-{index}'; keys.append(key)
            meta, _ = evidence(key, frames=144000, size_bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                               acquisition_start_us=100 + index * 4000000, acquisition_end_us=3000100 + index * 4000000)
            await self.send('capture_start', metadata=meta)
            for offset in range(0, len(raw), 4096):
                await self.send('capture_chunk', capture_id=key, offset=offset,
                                data=base64.b64encode(raw[offset:offset + 4096]).decode())
            await self.send('capture_end', capture_id=key, sha256=meta['sha256'])
            if index == 0:
                await self.turn('r1', keys)
                await self.send('ack', request_id='r1')
        await self.turn('r2', keys, adjustment='Moved to B as guided')
        await self.send('ack', request_id='r2')
        self.assertEqual(self.service.phase, 'complete')
        self.assertEqual(self.service.archive.used_bytes, 3 * 1152000)


try:
    import websockets
except ImportError:
    websockets = None


@unittest.skipIf(websockets is None, 'install tools/investigation-requirements.txt for real WebSocket tests')
class RepeatWebSocketTests(unittest.IsolatedAsyncioTestCase):
    async def test_walking_back_to_a_is_operator_paced(self):
        import asyncio
        from websockets.asyncio.client import connect
        from tools.investigation_service import serve_mock
        with tempfile.TemporaryDirectory() as directory:
            server = await serve_mock('127.0.0.1', 0, Path(directory), idle_s=0.3, operator_idle_s=5)
            async with server:
                uri = f'ws://127.0.0.1:{server.sockets[0].getsockname()[1]}'
                async with connect(uri, proxy=None) as socket:
                    async def send(kind, **fields):
                        await socket.send(json.dumps(dict(version=1, type=kind, boot_id='boot',
                                                          session_id='session', **fields)))
                    async def receive(): return json.loads(await asyncio.wait_for(socket.recv(), 2))
                    async def upload(key, amplitude, **fields):
                        meta, raw = evidence(key, amplitude, **fields)
                        await send('capture_start', metadata=meta); await receive()
                        for offset in range(0, len(raw), 4096):
                            await send('capture_chunk', capture_id=key, offset=offset,
                                       data=base64.b64encode(raw[offset:offset + 4096]).decode())
                        await send('capture_end', capture_id=key, sha256=meta['sha256'])
                        return await receive()
                    await send('hello', fixture=fixture().to_dict()); await receive()
                    await upload('take-a', 1000)
                    await send('turn', request_id='r1', capture_ids=['take-a'], device_ms=100, deadline_ms=15100)
                    await receive(); await send('ack', request_id='r1'); await receive()
                    await upload('take-b', 500, **A_TO_B)
                    await asyncio.sleep(0.8)  # walking back to A
                    self.assertEqual((await upload('take-r', 900, **REPEAT))['stage'], 'complete')


if __name__ == '__main__':
    unittest.main()
