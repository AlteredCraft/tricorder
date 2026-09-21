import asyncio
import base64
import json
from pathlib import Path
import tempfile
import unittest

from tools.investigation import ProtocolError
from tools.investigation_service import MockSession, decode_message
from test_investigation import evidence, fixture


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.sent = []
        async def send(message):self.sent.append(message)
        self.service = MockSession(self.root, send)
        await self.send('hello',fixture=fixture().to_dict())

    async def asyncTearDown(self):
        await self.service.close()

    async def send(self, kind, **fields):
        return await self.service.receive(dict(version=1,type=kind,boot_id='boot',session_id='session',**fields))

    async def capture(self, key='take-a', amplitude=1000, **fields):
        meta, raw = evidence(key,amplitude,**fields)
        await self.send('capture_start',metadata=meta)
        for offset in range(0,len(raw),4096):
            await self.send('capture_chunk',capture_id=key,offset=offset,
                            data=base64.b64encode(raw[offset:offset+4096]).decode())
        await self.send('capture_end',capture_id=key,sha256=meta['sha256'])

    async def turn(self, request_id, ids, **fields):
        await self.send('turn',request_id=request_id,capture_ids=ids,device_ms=100,
                        deadline_ms=15100,**fields)
        await self.service.drain()
        return self.sent[-1]

    async def test_complete_mock_service_uses_uploaded_bytes_and_acks(self):
        await self.capture()
        reply=await self.turn('r1',['take-a'])
        self.assertEqual(reply['type'],'guidance')
        await self.send('ack',request_id='r1')
        await self.capture('take-b',500,acquisition_start_us=30000,acquisition_end_us=50000)
        reply=await self.turn('r2',['take-a','take-b'],adjustment='Moved to 40 cm')
        self.assertAlmostEqual(reply['comparison']['rms_delta_db'],-6.020599913)
        await self.send('ack',request_id='r2')
        self.assertEqual(self.service.phase,'complete')
        run=self.root/'boot-session'
        self.assertEqual(len(list((run/'captures').glob('*.bin'))),2)
        transcript=(run/'transcript.jsonl').read_text()
        self.assertIn('Moved to 40 cm',transcript)
        self.assertNotIn(base64.b64encode(evidence()[1]).decode(),transcript)

    async def test_duplicate_unknown_expired_cross_session_and_ack_order(self):
        await self.capture()
        for fields in ({'capture_ids':['missing']},{'deadline_ms':100},{'session_id':'old'},
                       {'boot_id':'old'},{'capture_ids':[]}):
            message=dict(version=1,type='turn',boot_id='boot',session_id='session',request_id='r1',
                         capture_ids=['take-a'],device_ms=100,deadline_ms=15100)
            message.update(fields)
            with self.subTest(fields=fields),self.assertRaises(ProtocolError):
                await self.service.receive(message)
        await self.turn('r1',['take-a'])
        with self.assertRaises(ProtocolError):await self.turn('r1',['take-a'])
        with self.assertRaises(ProtocolError):await self.capture('take-b')
        with self.assertRaises(ProtocolError):await self.send('ack',request_id='wrong')
        await self.send('ack',request_id='r1')

    async def test_cancel_during_delay_is_immediate_and_late_result_is_discarded(self):
        self.service.delay_s=5
        await self.capture()
        await self.send('turn',request_id='r1',capture_ids=['take-a'],device_ms=100,deadline_ms=15100)
        await asyncio.wait_for(self.send('cancel'),timeout=.2)
        await self.service.drain()
        self.assertEqual(self.service.phase,'cancelled')
        self.assertFalse(any(x['type']=='guidance' for x in self.sent))
        with self.assertRaises(ProtocolError):await self.send('ack',request_id='r1')

    async def test_disconnect_retains_partial_and_reconnect_cannot_reuse_session(self):
        meta,raw=evidence()
        await self.send('capture_start',metadata=meta)
        await self.send('capture_chunk',capture_id='take-a',offset=0,data=base64.b64encode(raw[:100]).decode())
        await self.service.close()
        meta=json.loads((self.root/'boot-session/captures/take-a.json').read_text())
        self.assertEqual(meta['status'],'incomplete')
        self.assertEqual(meta['received_bytes'],100)
        async def send(_):pass
        other=MockSession(self.root,send)
        with self.assertRaises(FileExistsError):
            await other.receive(dict(version=1,type='hello',boot_id='boot',session_id='session',fixture=fixture().to_dict()))

    async def test_bad_transfer_fails_closed_and_preserves_partial(self):
        meta,_=evidence()
        await self.send('capture_start',metadata=meta)
        with self.assertRaises(ProtocolError):
            await self.send('capture_chunk',capture_id='take-a',offset=4,data='YQ==')
        self.assertEqual(self.service.phase,'incomplete')
        with self.assertRaises(ProtocolError):await self.send('capture_end',capture_id='take-a',sha256=meta['sha256'])

    async def test_deadline_expires_during_mock_delay(self):
        self.service.delay_s=.03
        await self.capture()
        await self.send('turn',request_id='r1',capture_ids=['take-a'],device_ms=100,deadline_ms=101)
        await self.service.drain()
        self.assertEqual(self.service.phase,'incomplete')
        self.assertFalse(any(x['type']=='guidance' for x in self.sent))

    async def test_full_three_second_pair_fits_all_wire_and_archive_budgets(self):
        import hashlib
        await self.service.close()
        f=fixture().to_dict();f['frames']=144000
        self.service=MockSession(self.root/'full',self.service.send)
        await self.send('hello',fixture=f)
        raw=evidence()[1][:8]*144000
        for index in range(2):
            key=f'full-{index}'
            meta,_=evidence(key,frames=144000,size_bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),
                            acquisition_start_us=100+index*4000000,acquisition_end_us=3000100+index*4000000)
            await self.send('capture_start',metadata=meta)
            for offset in range(0,len(raw),4096):
                await self.send('capture_chunk',capture_id=key,offset=offset,
                                data=base64.b64encode(raw[offset:offset+4096]).decode())
            await self.send('capture_end',capture_id=key,sha256=meta['sha256'])
            fields={'adjustment':'Moved to 40 cm'} if index else {}
            await self.turn(f'r{index}',[f'full-{i}' for i in range(index+1)],**fields)
            await self.send('ack',request_id=f'r{index}')
        self.assertEqual(self.service.phase,'complete')
        self.assertEqual(self.service.archive.used_bytes,2304000)
        with self.assertRaises(ProtocolError):await self.send('capture_start',metadata=meta)

    async def test_modified_saved_evidence_is_rejected_before_provider_call(self):
        await self.capture()
        (self.root/'boot-session/captures/take-a.bin').write_bytes(b'changed')
        with self.assertRaises(ProtocolError):await self.turn('r1',['take-a'])
        self.assertIsNone(self.service.task)

    async def test_stalled_async_provider_is_bounded_by_deadline(self):
        async def stalled(_):await asyncio.Event().wait()
        self.service.provider_reply=stalled
        await self.capture()
        await self.send('turn',request_id='r1',capture_ids=['take-a'],device_ms=100,deadline_ms=110)
        await asyncio.wait_for(self.service.drain(),.2)
        self.assertEqual(self.service.phase,'incomplete')
        self.assertEqual(self.sent[-1]['reason'],'deadline')

    async def test_future_provider_uses_same_reference_contract_and_sanitized_failure(self):
        async def invented(request):
            reply=self.service.provider.respond(request)
            reply['capture_ids']=['invented']
            return reply
        self.service.provider_reply=invented
        await self.capture()
        await self.turn('r1',['take-a'])
        self.assertEqual(self.service.phase,'incomplete')
        self.assertEqual(self.sent[-1]['reason'],'provider_or_evidence_failure')
        self.assertFalse(any(x['type']=='guidance' for x in self.sent))

    async def test_capture_and_command_queue_capacity(self):
        self.service.delay_s=5
        await self.capture()
        await self.send('turn',request_id='r1',capture_ids=['take-a'],device_ms=100,deadline_ms=15100)
        with self.assertRaises(ProtocolError):
            await self.send('turn',request_id='r2',capture_ids=['take-a'],device_ms=100,deadline_ms=15100)
        with self.assertRaises(ProtocolError):await self.capture('take-b')
        await self.send('cancel')


class WireTests(unittest.TestCase):
    def test_reject_duplicate_keys_nan_binary_and_oversized_messages(self):
        for wire in ('{"type":"a","type":"b"}', '{"x":NaN}', '[]', b'{}', ' '*32769):
            with self.subTest(wire=repr(wire[:50])),self.assertRaises(ProtocolError):decode_message(wire)



try:
    import websockets
except ImportError:
    websockets=None


@unittest.skipIf(websockets is None,'install tools/investigation-requirements.txt for real WebSocket tests')
class WebSocketTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_connection_upload_reply_cancel_and_session_capacity(self):
        from websockets.asyncio.client import connect
        from tools.investigation_service import serve_mock
        with tempfile.TemporaryDirectory() as directory:
            server=await serve_mock('127.0.0.1',0,Path(directory),delay_s=5,max_sessions=1)
            async with server:
                uri=f'ws://127.0.0.1:{server.sockets[0].getsockname()[1]}'
                async with connect(uri,proxy=None) as socket:
                    async def send(kind,**fields):
                        await socket.send(json.dumps(dict(version=1,type=kind,boot_id='boot',session_id='session',**fields)))
                    async def receive():return json.loads(await asyncio.wait_for(socket.recv(),1))
                    await send('hello',fixture=fixture().to_dict())
                    self.assertEqual((await receive())['type'],'ready')
                    meta,raw=evidence()
                    await send('capture_start',metadata=meta)
                    self.assertEqual((await receive())['stage'],'start')
                    for offset in range(0,len(raw),4096):
                        await send('capture_chunk',capture_id='take-a',offset=offset,
                                   data=base64.b64encode(raw[offset:offset+4096]).decode())
                    await send('capture_end',capture_id='take-a',sha256=meta['sha256'])
                    self.assertEqual((await receive())['stage'],'complete')
                    await send('turn',request_id='r1',capture_ids=['take-a'],device_ms=100,deadline_ms=15100)
                    await send('cancel')
                    self.assertEqual((await receive())['type'],'cancelled')
                async with connect(uri,proxy=None) as socket:
                    with self.assertRaises(websockets.exceptions.ConnectionClosed):await socket.recv()
            self.assertEqual(json.loads((Path(directory)/'boot-session/captures/take-a.json').read_text())['status'],'complete')

    async def test_real_connection_complete_ab(self):
        from websockets.asyncio.client import connect
        from tools.investigation_service import serve_mock
        with tempfile.TemporaryDirectory() as directory:
            server=await serve_mock('127.0.0.1',0,Path(directory))
            async with server:
                uri=f'ws://127.0.0.1:{server.sockets[0].getsockname()[1]}'
                async with connect(uri,proxy=None) as socket:
                    async def send(kind,**fields):
                        await socket.send(json.dumps(dict(version=1,type=kind,boot_id='boot',session_id='session',**fields)))
                    async def receive():return json.loads(await asyncio.wait_for(socket.recv(),1))
                    await send('hello',fixture=fixture().to_dict());await receive()
                    for index, amplitude in enumerate((1000,500)):
                        key=f'take-{index}'
                        meta,raw=evidence(key,amplitude,acquisition_start_us=100+index*30000,
                                          acquisition_end_us=20100+index*30000)
                        await send('capture_start',metadata=meta);await receive()
                        for offset in range(0,len(raw),4096):
                            await send('capture_chunk',capture_id=key,offset=offset,
                                       data=base64.b64encode(raw[offset:offset+4096]).decode())
                        await send('capture_end',capture_id=key,sha256=meta['sha256']);await receive()
                        fields={'adjustment':'Moved to 40 cm'} if index else {}
                        await send('turn',request_id=f'r{index}',capture_ids=[f'take-{i}' for i in range(index+1)],
                                   device_ms=100,deadline_ms=15100,**fields)
                        reply=await receive()
                        if index:self.assertAlmostEqual(reply['comparison']['rms_delta_db'],-6.020599913)
                        await send('ack',request_id=f'r{index}')
                        self.assertEqual((await receive())['state'],'complete' if index else 'adjust')


if __name__=='__main__':unittest.main()
