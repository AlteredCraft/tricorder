"""Single-device LAN WebSocket mock for G-0002.01 (no model keys required).

Start with: python -m tools.investigation_service --output .local/runs/ab-mock
The device owns UI deadlines and local cancel; this service never initiates a
capture. See planning/guided-ab-protocol.md for the experimental wire contract.
"""
import argparse
import asyncio
from contextlib import suppress
import json
from pathlib import Path
import time

from tools.captures import CaptureStore
from tools.investigation import (CaptureEvidence, Fixture, MAX_CAPTURE_BYTES, MockProvider,
                                 ProtocolError, RunArchive, bounded_text, identity,
                                 integer, require, validate_reply)

MAX_WIRE_BYTES = 32768


def decode_message(wire):
    require(isinstance(wire,str) and len(wire.encode())<=MAX_WIRE_BYTES, 'wire message size/type')
    def pairs(items):
        result={}
        for key,value in items:
            require(key not in result,'duplicate JSON key')
            result[key]=value
        return result
    def constant(_):raise ProtocolError('non-finite JSON number')
    try:
        result=json.loads(wire,object_pairs_hook=pairs,parse_constant=constant)
    except (ValueError,RecursionError) as error:
        raise ProtocolError('invalid JSON') from error
    require(isinstance(result,dict),'message must be an object')
    return result


class MockSession:
    def __init__(self, root, send, *, provider=None, delay_s=0, replay_only=False):
        self.root=Path(root)
        self.send=send
        self.provider=provider or MockProvider()
        self.delay_s=delay_s
        self.replay_only=replay_only
        self.archive=self.store=self.pending=self.task=None
        self.phase='new'
        self.ids=[]
        self.requests=set()
        self.reserved_bytes=0
        self.messages=0
        self.closed=False
        self.expires=0

    async def emit(self, message):
        self.archive.record({'direction':'out','payload':message})
        await self.send(message)

    def envelope(self, kind, **fields):
        return dict(version=1,type=kind,boot_id=self.archive.boot_id,
                    session_id=self.archive.session_id,**fields)

    async def receive(self, message):
        require(not self.closed and isinstance(message,dict),'closed/invalid session')
        require(type(message.get('version')) is int and message['version']==1,'protocol version')
        kind=message.get('type')
        fields={
            'hello':{'fixture'}, 'capture_start':{'metadata'},
            'capture_chunk':{'capture_id','offset','data'}, 'capture_end':{'capture_id','sha256'},
            'turn':{'request_id','capture_ids','device_ms','deadline_ms'},
            'ack':{'request_id'}, 'cancel':set()}
        require(isinstance(kind,str) and kind in fields,'unknown message type')
        allowed={'version','type','boot_id','session_id'}|fields[kind]
        if kind=='hello' and self.replay_only:allowed.add('replay')
        require(set(message)==allowed or (kind=='turn' and set(message)==allowed|{'adjustment'}), 'message fields')
        require(self.messages<640,'message budget exhausted')
        self.messages+=1
        if kind=='hello':
            require(self.phase=='new','duplicate hello')
            require(message.get('replay',False) is self.replay_only,'replay mode mismatch')
            try:fixture=Fixture(**message['fixture'])
            except (TypeError,KeyError) as error:raise ProtocolError('invalid fixture') from error
            boot,session=identity(message['boot_id']),identity(message['session_id'])
            self.archive=RunArchive(self.root/f'{boot}-{session}',boot,session,fixture)
            if self.replay_only:
                path=self.archive.root/'manifest.json'
                manifest=json.loads(path.read_text())
                manifest.update(replay=True,workload='SD replay; no new sensor acquisition',
                                scope='Transport replay of stored evidence; not a new physical A/B run')
                path.write_text(json.dumps(manifest,indent=2)+'\n')
            self.store=CaptureStore(self.archive.root/'captures')
            self.store.MAX_BYTES=MAX_CAPTURE_BYTES
            self.store.MAX_ACTIVE=1
            self.phase='await_a'
            self.archive.record({'direction':'in','payload':message})
            await self.emit(self.envelope('ready',provider=self.provider.name))
            return
        require(self.archive is not None,'hello required')
        require(message['boot_id']==self.archive.boot_id and message['session_id']==self.archive.session_id,
                'session mismatch')
        # Never log media/base64 or arbitrary extra fields. Raw evidence stays in captures/.
        if kind!='capture_chunk':self.archive.record({'direction':'in','payload':message})
        if kind=='cancel':
            require(self.phase not in ('complete','cancelled'),'terminal session')
            self.phase='cancelled';self.pending=None
            if self.task:self.task.cancel()
            self.store.close()
            await self.emit(self.envelope('cancelled'))
            return
        require(self.phase not in ('complete','cancelled','offline','incomplete'),'terminal session')
        if kind.startswith('capture_'):
            await self.capture(kind,message)
        elif kind=='turn':
            require(self.phase in ('guide_ready','compare_ready') and self.pending is None,'pending queue/state')
            request_id=identity(message['request_id'])
            require(request_id not in self.requests and len(self.requests)<2,'duplicate/request capacity')
            require(message['capture_ids']==self.ids,'unknown/out-of-order capture references')
            now=integer(message['device_ms'],0,2**53-60001)
            deadline=integer(message['deadline_ms'],now+1,now+60000)
            adjustment=message.get('adjustment')
            if len(self.ids)==2:bounded_text(adjustment,512)
            else:require(adjustment is None,'premature adjustment')
            request=dict(version=1,type='guide' if len(self.ids)==1 else 'compare',
                         boot_id=self.archive.boot_id,session_id=self.archive.session_id,
                         request_id=request_id,deadline_ms=deadline,fixture=self.archive.fixture.to_dict(),
                         adjustment=adjustment,captures=[self.archive.load(key).to_dict() for key in self.ids])
            self.pending=request
            self.requests.add(request_id)
            self.expires=time.monotonic()+(deadline-now)/1000
            self.phase='pending'
            self.task=asyncio.create_task(self.respond(request))
        elif kind=='ack':
            require(self.phase=='await_ack' and self.pending is not None,'no response awaiting acknowledgement')
            require(time.monotonic()<self.expires,'ack deadline expired')
            require(message['request_id']==self.pending['request_id'],'ack mismatch')
            self.pending=None
            self.phase='adjust' if len(self.ids)==1 else 'complete'
            await self.emit(self.envelope('acknowledged',request_id=message['request_id'],state=self.phase))

    async def capture(self, kind, message):
        if kind=='capture_start':
            require(self.phase in ('await_a','adjust'),'capture invalid in state')
            meta=message['metadata']
            require(isinstance(meta,dict),'capture metadata')
            key=identity(meta.get('capture_id'))
            require(meta.get('boot_id')==self.archive.boot_id and meta.get('session_id')==self.archive.session_id,
                    'capture identity mismatch')
            require(key not in self.store.seen and len(self.store.seen)<2,'capture capacity/duplicate')
            size=integer(meta.get('size_bytes'),1,MAX_CAPTURE_BYTES)
            require(self.reserved_bytes+size<=self.archive.max_bytes,'capture byte capacity')
            # Only these transport fields can identify the event; metadata cannot override them.
            self.store.consume({**meta,'event':'capture_start'})
            self.reserved_bytes+=size
            self.phase='recording_a' if not self.ids else 'recording_b'
            await self.emit(self.envelope('capture_ack',capture_id=key,stage='start'))
            return
        require(self.phase in ('recording_a','recording_b'),'no active capture')
        try:
            self.store.consume({**message,'event':kind})
            if kind=='capture_end':
                key=message['capture_id']
                path=self.archive.root/'captures'/f'{key}.json'
                item=CaptureEvidence.from_pcm(json.loads(path.read_text()),path.with_suffix('.bin').read_bytes())
                self.archive.fixture.check(item)
                if self.ids:
                    first=self.archive.load(self.ids[0])
                    require(item.metadata['acquisition_start_us']>=first.metadata['acquisition_end_us'],
                            'A/B windows overlap')
                self.archive.seen.add(key)
                self.archive.used_bytes+=len(item.raw)
                self.ids.append(key)
                self.phase='guide_ready' if len(self.ids)==1 else 'compare_ready'
                await self.emit(self.envelope('capture_ack',capture_id=key,stage='complete',sha256=item.metadata['sha256']))
        except (ValueError,KeyError,TypeError) as error:
            self.phase='incomplete'
            self.store.close()
            raise ProtocolError('capture rejected') from error

    async def respond(self, request):
        try:
            async with asyncio.timeout(max(0,self.expires-time.monotonic())):
                await asyncio.sleep(self.delay_s)
                # Future network providers implement this awaitable seam. No synchronous
                # model call may block the receive/cancel loop.
                reply=await self.provider_reply(request)
            if self.pending is not request or self.phase!='pending':return
            if time.monotonic()>=self.expires:
                self.phase='incomplete';self.pending=None
                await self.emit(self.envelope('incomplete',reason='deadline'))
                return
            validate_reply(request,reply)
            self.phase='await_ack'
            await self.emit(reply)
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            self.phase='incomplete';self.pending=None
            await self.emit(self.envelope('incomplete',reason='deadline'))
        except Exception:
            self.phase='incomplete';self.pending=None
            # Exceptions from future providers can include URLs/keys; record only a fixed reason.
            await self.emit(self.envelope('incomplete',reason='provider_or_evidence_failure'))

    async def provider_reply(self, request):
        return self.provider.respond(request)

    async def drain(self):
        if self.task:
            with suppress(asyncio.CancelledError):await self.task

    async def close(self):
        if self.closed:return
        self.closed=True
        if self.task:self.task.cancel()
        await self.drain()
        if self.store:
            incomplete=self.store.close()
            if self.phase not in ('complete','cancelled','incomplete'):self.phase='offline'
            self.pending=None
            self.archive.record({'type':'closed','state':self.phase,'incomplete_captures':incomplete})


async def serve_mock(host, port, output, *, delay_s=0, max_sessions=32, replay_only=False):
    from websockets.asyncio.server import serve
    from websockets.exceptions import ConnectionClosed
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True,mode=0o700)
    active=False
    async def handler(socket):
        nonlocal active
        if active or sum(1 for _ in output.iterdir())>=max_sessions:
            await socket.close(code=1013,reason='session capacity');return
        active=True
        async def send(message):
            await asyncio.wait_for(socket.send(json.dumps(message,allow_nan=False)),timeout=2)
        session=MockSession(output,send,delay_s=delay_s,replay_only=replay_only)
        try:
            while True:
                wire=await asyncio.wait_for(socket.recv(),timeout=30)
                await session.receive(decode_message(wire))
        except ConnectionClosed as error:
            if session.archive:
                session.archive.record({'type':'transport_closed',
                    'received_code':error.rcvd.code if error.rcvd else None,
                    'sent_code':error.sent.code if error.sent else None})
        except (ValueError,TypeError,KeyError,TimeoutError,OSError,RecursionError):
            # Do not echo payloads, credentials or exception text into public logs.
            if session.archive:
                session.phase='incomplete'
                with suppress(ValueError,OSError):session.archive.record({'type':'rejected','reason':'protocol_or_io'})
            await socket.close(code=1008,reason='protocol, timeout or storage failure')
        finally:
            try:await session.close()
            finally:active=False
    return await serve(handler,host,port,compression=None,max_size=MAX_WIRE_BYTES,
                       max_queue=4,write_limit=32768,open_timeout=5,close_timeout=2,
                       ping_interval=10,ping_timeout=10)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',default='127.0.0.1',help='Use the Mac LAN IP for handheld trials')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--delay-seconds',type=float,default=0,help='Controlled mock-response delay, 0–30')
    parser.add_argument('--replay-only',action='store_true',help='Require labeled SD replay; no new physical trial')
    args=parser.parse_args()
    if not 0<=args.delay_seconds<=30:parser.error('delay must be 0–30 seconds')
    async def run():
        server=await serve_mock(args.host,args.port,args.output,delay_s=args.delay_seconds,replay_only=args.replay_only)
        print(f'Mock ready at ws://{args.host}:{args.port}; private evidence: {args.output}',flush=True)
        async with server:await server.serve_forever()
    try:asyncio.run(run())
    except KeyboardInterrupt:pass


if __name__=='__main__':main()
