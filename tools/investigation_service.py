"""Single-device LAN WebSocket mock for G-0002.01 (no model keys required).

Start with: python -m tools.investigation_service --output .local/runs/ab-mock
The device owns UI deadlines and local cancel; this service never initiates a
capture. See planning/guided-ab-protocol.md for the experimental wire contract.
"""
import argparse
import base64
import asyncio
from contextlib import suppress
import json
import inspect
from pathlib import Path
import time
import wave

from tools.captures import CaptureStore
from tools.speech_to_text import DEFAULT_ENGINE, ENGINES, load_transcriber
from tools import text_to_speech
from tools.investigation import (CaptureEvidence, Fixture, MAX_CAPTURE_BYTES, MAX_QUESTIONS,
                                 MAX_QUESTION_FRAMES, MAX_QUESTION_TEXT, MockProvider,
                                 ProtocolError, QUESTION_FIELDS, QUESTION_RATE_HZ, QuestionAudio,
                                 RunArchive, bounded_text, device_text, identity, integer, require,
                                 validate_reply)

MAX_WIRE_BYTES = 32768
# A, B and a repeat of A: start + 282 chunks + end each, plus hello, turns, acks, cancel.
MAX_MESSAGES = 900
# Spoken ask: start + chunks + end + confirm per question, outside the A/B budget.
QUESTION_MESSAGES = MAX_QUESTIONS*(-(-MAX_QUESTION_FRAMES*2//4096)+3)
# Spoken guidance: 24 kHz mono s16 in chunks of at most 4096 bytes, at most 60 s per reply.
SPEECH_RATE_HZ = text_to_speech.RATE_HZ
MAX_SPEECH_FRAMES = 60*SPEECH_RATE_HZ


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
    def __init__(self, root, send, *, provider=None, delay_s=0, replay_only=False, transcriber=None, speaker=None):
        self.root=Path(root)
        self.send=send
        self.provider=provider or MockProvider()
        self.transcriber=transcriber
        self.transcribe_timeout_s=10
        self.delay_s=delay_s
        self.replay_only=replay_only
        self.archive=self.store=self.pending=self.task=None
        self.phase='new'
        self.ids=[]
        self.requests=set()
        self.reserved_bytes=0
        self.messages=0
        # Spoken ask (ADR-0013): separate IDs, store and budget; never a measurement.
        self.question_store=self.heard=self.operator_question=None
        self.question_ids=[]
        self.question_messages=0
        # Spoken guidance: the checked text of each acknowledged reply, spoken once on request.
        self.speaker=speaker
        self.replies={}
        self.acknowledged=self.speaking=self.speech_task=None
        self.spoken=set()
        self.speech_stop=asyncio.Event()
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
            'ack':{'request_id'}, 'cancel':set(),
            'question_start':{'metadata'}, 'question_chunk':{'question_id','offset','data'},
            'question_end':{'question_id','sha256'}, 'question_confirm':{'question_id','accepted'},
            'speak':{'request_id'}, 'speech_stop':{'request_id'}}
        require(isinstance(kind,str) and kind in fields,'unknown message type')
        allowed={'version','type','boot_id','session_id'}|fields[kind]
        if kind=='hello' and self.replay_only:allowed.add('replay')
        require(set(message)==allowed or (kind=='turn' and set(message)==allowed|{'adjustment'}), 'message fields')
        if kind.startswith('question_'):
            require(self.question_messages<QUESTION_MESSAGES,'question message budget exhausted')
            self.question_messages+=1
        else:
            require(self.messages<MAX_MESSAGES,'message budget exhausted')
            self.messages+=1
        if kind=='hello':
            require(self.phase=='new','duplicate hello')
            require(message.get('replay',False) is self.replay_only,'replay mode mismatch')
            try:fixture=Fixture(**message['fixture'])
            except (TypeError,KeyError) as error:raise ProtocolError('invalid fixture') from error
            boot,session=identity(message['boot_id']),identity(message['session_id'])
            # A saved session may be replayed many times (G-0001.02 baselines); each
            # replay is its own run. A live session ID is never reused.
            name=f'{boot}-{session}'
            if self.replay_only:
                name=next(n for n in (name,*(f'{name}-{i}' for i in range(2,1000)))
                          if not (self.root/n).exists())
            self.archive=RunArchive(self.root/name,boot,session,fixture)
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
            speech=self.transcriber.name if self.transcriber and not self.replay_only else None
            voice=self.speaker.name if self.speaker else None
            await self.emit(self.envelope('ready',provider=self.provider.name,speech_to_text=speech,speech_output=voice))
            return
        require(self.archive is not None,'hello required')
        require(message['boot_id']==self.archive.boot_id and message['session_id']==self.archive.session_id,
                'session mismatch')
        # Never log media/base64 or arbitrary extra fields. Raw evidence stays in captures/.
        if kind not in ('capture_chunk','question_chunk'):self.archive.record({'direction':'in','payload':message})
        # While a reply is being spoken the device may only stop it or cancel.
        require(self.speaking is None or kind in ('speech_stop','cancel'),'speech in progress')
        if kind=='cancel':
            require(self.phase not in ('complete','cancelled'),'terminal session')
            self.phase='cancelled';self.pending=None
            if self.task:self.task.cancel()
            if self.speech_task:self.speech_task.cancel()
            self.store.close()
            if self.question_store:self.question_store.close()
            await self.emit(self.envelope('cancelled'))
            return
        if kind in ('speak','speech_stop'):
            await self.speech(kind,message)
            return
        require(self.phase not in ('complete','cancelled','offline','incomplete'),'terminal session')
        if kind.startswith('question_'):
            await self.question(kind,message)
        elif kind.startswith('capture_'):
            await self.capture(kind,message)
        elif kind=='turn':
            require(self.phase in ('guide_ready','compare_ready') and self.pending is None,'pending queue/state')
            request_id=identity(message['request_id'])
            require(request_id not in self.requests and len(self.requests)<2,'duplicate/request capacity')
            require(message['capture_ids']==self.ids,'unknown/out-of-order capture references')
            now=integer(message['device_ms'],0,2**53-60001)
            deadline=integer(message['deadline_ms'],now+1,now+60000)
            adjustment=message.get('adjustment')
            if len(self.ids)>1:bounded_text(adjustment,512)
            else:require(adjustment is None,'premature adjustment')
            request=dict(version=1,type='guide' if len(self.ids)==1 else 'compare',
                         boot_id=self.archive.boot_id,session_id=self.archive.session_id,
                         request_id=request_id,deadline_ms=deadline,fixture=self.archive.fixture.to_dict(),
                         adjustment=adjustment,operator_question=self.operator_question,
                         captures=[self.archive.load(key).to_dict() for key in self.ids])
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
            self.acknowledged=message['request_id']
            self.phase='adjust' if len(self.ids)==1 else 'complete'
            await self.emit(self.envelope('acknowledged',request_id=message['request_id'],state=self.phase))

    async def capture(self, kind, message):
        if kind=='capture_start':
            # compare_ready: after B the device may record A again before the compare turn.
            require(self.phase in ('await_a','adjust') or (self.phase=='compare_ready' and len(self.ids)==2),
                    'capture invalid in state')
            meta=message['metadata']
            require(isinstance(meta,dict),'capture metadata')
            key=identity(meta.get('capture_id'))
            require(meta.get('boot_id')==self.archive.boot_id and meta.get('session_id')==self.archive.session_id,
                    'capture identity mismatch')
            require(key not in self.store.seen and len(self.store.seen)<3,'capture capacity/duplicate')
            require(key not in self.question_ids,'capture ID reuses a question ID')
            size=integer(meta.get('size_bytes'),1,MAX_CAPTURE_BYTES)
            require(self.reserved_bytes+size<=self.archive.max_bytes,'capture byte capacity')
            # Only these transport fields can identify the event; metadata cannot override them.
            self.store.consume({**meta,'event':'capture_start'})
            self.reserved_bytes+=size
            self.phase=('recording_a','recording_b','recording_repeat')[len(self.ids)]
            await self.emit(self.envelope('capture_ack',capture_id=key,stage='start'))
            return
        require(self.phase in ('recording_a','recording_b','recording_repeat'),'no active capture')
        try:
            self.store.consume({**message,'event':kind})
            if kind=='capture_end':
                key=message['capture_id']
                path=self.archive.root/'captures'/f'{key}.json'
                item=CaptureEvidence.from_pcm(json.loads(path.read_text()),path.with_suffix('.bin').read_bytes())
                self.archive.fixture.check(item)
                if self.ids:
                    last=self.archive.load(self.ids[-1])
                    require(item.metadata['acquisition_start_us']>=last.metadata['acquisition_end_us'],
                            'capture windows overlap')
                self.archive.seen.add(key)
                self.archive.used_bytes+=len(item.raw)
                self.ids.append(key)
                self.phase='guide_ready' if len(self.ids)==1 else 'compare_ready'
                await self.emit(self.envelope('capture_ack',capture_id=key,stage='complete',sha256=item.metadata['sha256']))
        except (ValueError,KeyError,TypeError) as error:
            self.phase='incomplete'
            self.store.close()
            raise ProtocolError('capture rejected') from error

    async def question(self, kind, message):
        if kind=='question_start':
            require(self.transcriber is not None and not self.replay_only,'speech-to-text unavailable')
            require(self.phase=='await_a' and not self.ids,'questions only before Record A')
            require(len(self.question_ids)<MAX_QUESTIONS,'question capacity')
            meta=message['metadata']
            require(isinstance(meta,dict) and set(meta)==QUESTION_FIELDS,'question metadata fields')
            key=identity(meta['question_id'])
            require(meta['boot_id']==self.archive.boot_id and meta['session_id']==self.archive.session_id,
                    'question identity mismatch')
            require(key not in self.question_ids and key not in self.store.seen,'question ID reused')
            integer(meta['size_bytes'],1,MAX_QUESTION_FRAMES*2)
            if self.question_store is None:
                self.question_store=CaptureStore(self.archive.root/'questions')
                self.question_store.MAX_BYTES=MAX_QUESTION_FRAMES*2
                self.question_store.MAX_ACTIVE=1
            self.question_store.consume({**meta,'capture_id':key,'event':'capture_start'})
            self.question_ids.append(key)
            self.phase='question_upload'
            return
        if kind=='question_confirm':
            require(self.phase=='await_confirm' and self.heard and message['question_id']==self.heard[0],
                    'no transcript awaiting confirmation')
            require(type(message['accepted']) is bool,'confirmation must be boolean')
            key,text=self.heard
            self.heard=None
            if message['accepted']:self.operator_question=text
            self.archive.record({'type':'operator_question','question_id':key,
                                 'accepted':message['accepted'],'text':text})
            self.phase='await_a'
            return
        require(self.phase=='question_upload' and message['question_id']==self.question_ids[-1],
                'no active question upload')
        key=message['question_id']
        try:
            event={k:v for k,v in message.items() if k!='question_id'}
            self.question_store.consume({**event,'capture_id':key,
                                        'event':'capture_chunk' if kind=='question_chunk' else 'capture_end'})
            if kind=='question_end':
                path=self.archive.root/'questions'/f'{key}.json'
                stored=json.loads(path.read_text())
                require(stored['status']=='complete','question upload incomplete')
                item=QuestionAudio.from_pcm({k:stored[k] for k in QUESTION_FIELDS},path.with_suffix('.bin').read_bytes())
                self.phase='transcribing'
                self.task=asyncio.create_task(self.transcribe(item))
        except (ValueError,KeyError,TypeError) as error:
            self.phase='incomplete'
            self.question_store.close()
            raise ProtocolError('question rejected') from error

    async def transcribe(self, item):
        """Transcribe off the receive loop. The device shows the text for Use or Retry;
        only a confirmed transcript becomes the operator question."""
        key=item.metadata['question_id']
        analysis=item.analysis
        started=time.monotonic_ns()
        status,text,reason='failed','',None
        try:
            async with asyncio.timeout(self.transcribe_timeout_s):
                heard=await self.transcriber.transcribe(item.raw)
            heard=' '.join(device_text(heard).split()) if isinstance(heard,str) else None
            if heard is None:reason='not_text'
            elif not heard:status='empty'
            elif len(heard.encode())>MAX_QUESTION_TEXT:reason='too_long'
            else:status,text='heard',heard
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            reason='timeout'
        except Exception:
            reason='engine_error'  # Engine exceptions can carry paths or keys; never log them.
        with wave.open(str(self.archive.root/'questions'/f'{key}.wav'),'wb') as stream:
            stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(QUESTION_RATE_HZ)
            stream.writeframes(item.raw)
        self.archive.record({'type':'question_analysis','question_id':key,
            'transcriber':self.transcriber.name,'status':status,'reason':reason,'text':text,
            'started_host_ns':started,'finished_host_ns':time.monotonic_ns(),**analysis})
        if self.phase!='transcribing':return
        self.heard=(key,text) if status=='heard' else None
        self.phase='await_confirm' if status=='heard' else 'await_a'
        level=analysis['speech_to_noise_db']
        await self.emit(self.envelope('transcript',question_id=key,status=status,text=text,
                                      speech_to_noise_db=None if level is None else round(level,1)))

    async def respond(self, request):
        try:
            async with asyncio.timeout(max(0,self.expires-time.monotonic())):
                await asyncio.sleep(self.delay_s)
                # Future network providers implement this awaitable seam. No synchronous
                # model call may block the receive/cancel loop.
                started=time.monotonic_ns()
                reply=await self.provider_reply(request)
                self.archive.record({'type':'provider_timing','request_id':request['request_id'],
                    'provider':self.provider.name,'model':getattr(self.provider,'model',None),
                    'started_host_ns':started,'finished_host_ns':time.monotonic_ns()})
            if self.pending is not request or self.phase!='pending':return
            if time.monotonic()>=self.expires:
                self.phase='incomplete';self.pending=None
                await self.emit(self.envelope('incomplete',reason='deadline'))
                return
            validate_reply(request,reply)
            self.phase='await_ack'
            self.replies[request['request_id']]=reply['text']
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
        reply=self.provider.respond(request)
        return await reply if inspect.isawaitable(reply) else reply

    async def speech(self, kind, message):
        key=message['request_id']
        if kind=='speech_stop':
            # A stop can cross an end already in flight; only a never-spoken reply is an error.
            require(key in self.spoken,'no speech to stop')
            if self.speaking==key:self.speech_stop.set()
            return
        require(self.speaker is not None,'speech output unavailable')
        require(self.phase in ('adjust','complete') and key==self.acknowledged and key not in self.spoken,
                'speak needs the latest acknowledged reply, once')
        self.spoken.add(key)
        self.speaking=key
        self.speech_stop=asyncio.Event()
        self.speech_task=asyncio.create_task(self.speak(key,self.replies[key]))

    async def speak(self, key, text):
        """Stream the checked text, verbatim, as it is synthesized. Chunks go straight to the
        socket: the transcript records the stream, and the samples are saved as a WAV."""
        started=time.monotonic_ns();first=None
        status,reason,frames,pending,audio='complete',None,0,bytearray(),bytearray()
        async def flush(final=False):
            nonlocal pending,frames
            while len(pending)>=4096 or (final and pending):
                data=bytes(pending[:4096]);pending=pending[4096:]
                await self.send(self.envelope('speech_chunk',request_id=key,offset=frames,
                                              data=base64.b64encode(data).decode()))
                frames+=len(data)//2
        try:
            await self.emit(self.envelope('speech_start',request_id=key,format='pcm_s16le',
                                          sample_rate_hz=SPEECH_RATE_HZ,channels=1))
            async for chunk in self.speaker.stream(text,self.speech_stop):
                first=first or time.monotonic_ns()
                room=MAX_SPEECH_FRAMES*2-len(audio)
                if len(chunk)>room:
                    chunk=chunk[:room];status,reason='failed','too_long'
                audio+=chunk;pending+=chunk
                await flush()
                if status=='failed':break
            await flush(final=True)
            if status=='complete' and self.speech_stop.is_set():status='stopped'
        except asyncio.CancelledError:
            raise
        except Exception:
            status,reason='failed','engine_error'  # engine errors can carry paths; never log them
            with suppress(Exception):await flush(final=True)
        finally:
            if len(audio)//2:
                (self.archive.root/'speech').mkdir(mode=0o700,exist_ok=True)
                with wave.open(str(self.archive.root/'speech'/f'{key}.wav'),'wb') as stream:
                    stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(SPEECH_RATE_HZ)
                    stream.writeframes(bytes(audio[:frames*2]))
            self.speaking=None
        self.archive.record({'type':'speech_output','request_id':key,'speaker':self.speaker.name,'status':status,
                             'reason':reason,'frames':frames,'started_host_ns':started,
                             'first_chunk_host_ns':first,'finished_host_ns':time.monotonic_ns()})
        await self.emit(self.envelope('speech_end',request_id=key,status=status,frames=frames))

    async def drain_speech(self):
        if self.speech_task:
            with suppress(asyncio.CancelledError):await self.speech_task

    async def drain(self):
        if self.task:
            with suppress(asyncio.CancelledError):await self.task

    async def close(self):
        if self.closed:return
        self.closed=True
        if self.task:self.task.cancel()
        if self.speech_task:self.speech_task.cancel()
        await self.drain()
        await self.drain_speech()
        if self.question_store:self.question_store.close()
        if self.store:
            incomplete=self.store.close()
            if self.phase not in ('complete','cancelled','incomplete'):self.phase='offline'
            self.pending=None
            self.archive.record({'type':'closed','state':self.phase,'incomplete_captures':incomplete})


# Phases where the device's next message waits for the person (record A; read the
# transcript; read guidance, move, record B; walk back to A). A read that starts while transcribing
# ends after the person reads it; transcription has its own bound. WebSocket
# ping/pong (10 s + 10 s) still detects a dead device. After complete the device may
# still be playing the spoken comparison before it closes.
OPERATOR_PHASES=('await_a','transcribing','await_confirm','adjust','compare_ready','complete')


async def serve_mock(host, port, output, *, delay_s=0, max_sessions=32, replay_only=False, provider=None,
                     idle_s=30, operator_idle_s=600, transcriber=None, speaker=None):
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
        session=MockSession(output,send,delay_s=delay_s,replay_only=replay_only,provider=provider,
                            transcriber=transcriber,speaker=speaker)
        try:
            while True:
                wire=await asyncio.wait_for(socket.recv(),
                    timeout=operator_idle_s if session.phase in OPERATOR_PHASES else idle_s)
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
    parser.add_argument('--replay-speech',action='store_true',
                        help='With --replay-only, also speak replayed guidance (--tts engine; G-0001.02 playback baseline)')
    parser.add_argument('--provider',choices=('mock','openai','openrouter'),default='mock')
    parser.add_argument('--model',help='Exact model ID; default OpenRouter openai/gpt-5.6-sol or direct gpt-4.1-mini')
    parser.add_argument('--env',type=Path,help='Local provider-key file; parsed literally, never sent to device')
    parser.add_argument('--stt',choices=ENGINES,default=DEFAULT_ENGINE,
                        help='Speech-to-text for spoken questions; parakeet is local (tools/stt-requirements.txt)')
    parser.add_argument('--tts',choices=text_to_speech.ENGINES,default=text_to_speech.DEFAULT_ENGINE,
                        help='Spoken guidance; pocket is local Pocket TTS "alba" (tools/tts-requirements.txt), say is macOS')
    args=parser.parse_args()
    if not 0<=args.delay_seconds<=30:parser.error('delay must be 0–30 seconds')
    transcriber=None
    if not args.replay_only and args.stt!='none':
        try:transcriber=load_transcriber(args.stt)
        except ImportError:parser.error('Local speech-to-text needs tools/stt-requirements.txt (Apple Silicon); or pass --stt none')
    speaker=None
    if args.replay_speech and not args.replay_only:parser.error('--replay-speech needs --replay-only')
    if (args.replay_speech or not args.replay_only) and args.tts!='none':
        try:speaker=text_to_speech.load_speaker(args.tts)
        except ImportError:parser.error('Pocket TTS needs tools/tts-requirements.txt; or pass --tts say or --tts none')
    async def run():
        client=None;provider=None
        if args.provider!='mock':
            from openai import AsyncOpenAI
            from tools.openai_provider import OpenAIProvider
            from tools.service_credentials import load_api_key
            router=args.provider=='openrouter'
            try:key=load_api_key(args.provider,args.env)
            except (ValueError,OSError):parser.error('Cannot load the selected provider key from local configuration')
            client=AsyncOpenAI(api_key=key,base_url='https://openrouter.ai/api/v1' if router else 'https://api.openai.com/v1',
                               timeout=12,max_retries=0)
            provider=OpenAIProvider(client,model=args.model or ('openai/gpt-5.6-sol' if router else 'gpt-4.1-mini'),route=args.provider)
        try:
            server=await serve_mock(args.host,args.port,args.output,delay_s=args.delay_seconds,
                                    replay_only=args.replay_only,provider=provider,transcriber=transcriber,
                                    speaker=speaker)
            speech=transcriber.name if transcriber else 'off'
            voice=speaker.name if speaker else 'off'
            print(f'{args.provider} service ready at ws://{args.host}:{args.port}; speech-to-text {speech}; '
                  f'spoken guidance {voice}; '
                  f'private evidence: {args.output}',flush=True)
            async with server:await server.serve_forever()
        finally:
            if client:await client.close()
    try:asyncio.run(run())
    except KeyboardInterrupt:pass


if __name__=='__main__':main()
