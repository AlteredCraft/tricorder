"""Run the firmware protocol against host-generated replies, including hostile ones."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from tools.investigation import CaptureEvidence, MockProvider
from test_investigation import evidence, fixture
from test_question import question


class DeviceProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        root = Path(cls.temp.name)
        source = root/'driver.cpp'
        source.write_text(r'''
#include "investigation_protocol.h"
#include <iostream>
#include <string>
#include <cstdlib>
#include <cmath>
static size_t allocated=0;
static void* tracked_malloc(size_t n){allocated+=n;return malloc(n);}
int main() {
 cJSON_Hooks hooks{tracked_malloc,free};cJSON_InitHooks(&hooks);
 InvestigationProtocol p("boot", "session", 960);
 std::string line;
 while(std::getline(std::cin,line)) {
  auto* cmd=cJSON_Parse(line.c_str());
  auto* op=cJSON_GetObjectItemCaseSensitive(cmd,"op");
  auto* now=cJSON_GetObjectItemCaseSensitive(cmd,"now");
  uint64_t t=now?static_cast<uint64_t>(now->valuedouble):100;
  bool ok=false; cJSON* out=nullptr;size_t capture_allocated=0;
  std::string action=op->valuestring;
  if(action=="ask") {ok=p.ask(t);}
  else if(action=="receive") {
   auto* wire=cJSON_GetObjectItemCaseSensitive(cmd,"wire");
   ok=p.receive(wire->valuestring,t);
  } else if(action=="start") ok=p.start_capture();
  else if(action=="captured") {
   auto* m=cJSON_GetObjectItemCaseSensitive(cmd,"metadata");
   auto* v=cJSON_GetObjectItemCaseSensitive(cmd,"measurement");
   size_t before=allocated;ok=p.captured(m,v,t);capture_allocated=allocated-before;
  } else if(action=="uploaded") {out=p.turn(t);ok=out;}
  else if(action=="adjust") ok=p.adjust("Moved to 40 cm");
  else if(action=="cancel") {p.cancel();ok=true;}
  else if(action=="disconnect") {p.disconnect();ok=true;}
  else if(action=="tick") {p.tick(t);ok=true;}
  else if(action=="ack") {out=p.ack();ok=out;}
  else if(action=="await_repeat") ok=p.await_repeat();
  else if(action=="start_question") ok=p.start_question();
  else if(action=="question_recorded") {
   ok=p.question_recorded(cJSON_GetObjectItemCaseSensitive(cmd,"metadata"),t);
  } else if(action=="confirm") {
   out=p.confirm_question(cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(cmd,"accepted")));ok=out;
  }
  auto* result=cJSON_CreateObject();
  cJSON_AddBoolToObject(result,"ok",ok);
  cJSON_AddNumberToObject(result,"capture_allocated",capture_allocated);
  cJSON_AddStringToObject(result,"state",p.state_name());
  cJSON_AddStringToObject(result,"text",p.text());
  cJSON_AddStringToObject(result,"question",p.question());
  cJSON_AddStringToObject(result,"transcript",p.transcript());
  cJSON_AddStringToObject(result,"status",p.transcript_status());
  cJSON_AddNumberToObject(result,"questions_left",p.questions_left());
  cJSON_AddNumberToObject(result,"speaks",p.speech_output());
  if(std::isfinite(p.speech_to_noise_db()))cJSON_AddNumberToObject(result,"snr",p.speech_to_noise_db());
  else cJSON_AddNullToObject(result,"snr");
  if(out)cJSON_AddItemToObject(result,"out",out);
  char* encoded=cJSON_PrintUnformatted(result);std::cout<<encoded<<std::endl;
  cJSON_free(encoded);cJSON_Delete(result);cJSON_Delete(cmd);
 }
}
''')
        cjson = Path('.tools/esp-idf/components/json/cJSON')
        result = subprocess.run(['clang','-c','-fsanitize=address',str(cjson/'cJSON.c'),
                                 '-o',str(root/'cJSON.o')],capture_output=True,text=True)
        if result.returncode:raise AssertionError(result.stderr)
        cls.binary = root/'driver'
        result = subprocess.run(['clang++','-std=c++17','-Wall','-Wextra','-Werror',
                                 '-fsanitize=address','-I','firmware/main','-I',str(cjson),
                                 str(source),'firmware/main/investigation_protocol.cpp',
                                 str(root/'cJSON.o'),'-o',str(cls.binary)],capture_output=True,text=True)
        if result.returncode:raise AssertionError(result.stderr)

    def run_commands(self, commands):
        r=subprocess.run([str(self.binary)],input=''.join(json.dumps(x)+'\n' for x in commands),
                         capture_output=True,text=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stderr)
        return [json.loads(line) for line in r.stdout.splitlines()]

    def envelope(self, kind, **fields):
        return dict(version=1,type=kind,boot_id='boot',session_id='session',**fields)

    def receive(self, payload, now=100):
        return dict(op='receive',wire=json.dumps(payload),now=now)

    def capture(self, key='take-a', amplitude=1000, start=1000):
        meta,raw=evidence(key,amplitude,acquisition_start_us=start,acquisition_end_us=start+1000)
        item=CaptureEvidence.from_pcm(meta,raw)
        return dict(op='captured',metadata=meta,measurement=item.measurement),item

    def prefix(self):
        capture,item=self.capture()
        return [dict(op='ask'),self.receive(self.envelope('ready',provider='scripted-mock-v1',speech_to_text='fake-stt',speech_output='fake-tts')),
                dict(op='start'),capture,dict(op='uploaded')],item

    def reply(self, items, deadline=15100):
        request=self.envelope('guide' if len(items)==1 else 'compare',request_id='r1' if len(items)==1 else 'r2',
                              deadline_ms=deadline,fixture=fixture().to_dict(),
                              captures=[x.to_dict() for x in items],adjustment='Moved to 40 cm')
        return MockProvider().respond(request)

    def ready(self, speech='fake-stt', voice='fake-tts'):
        return [dict(op='ask'),self.receive(self.envelope('ready',provider='scripted-mock-v1',speech_to_text=speech,
                                                              speech_output=voice))]

    def test_service_ready_is_accepted_and_names_speech_output(self):
        import asyncio
        from tools.investigation_service import MockSession
        from test_spoken_ask_service import FakeTranscriber
        from test_spoken_guidance import FakeSpeaker
        async def ready(**engines):
            sent=[]
            async def send(message):sent.append(message)
            with tempfile.TemporaryDirectory() as directory:
                service=MockSession(Path(directory),send,**engines)
                await service.receive(dict(version=1,type='hello',boot_id='boot',session_id='session',fixture=fixture().to_dict()))
                await service.close()
            return sent[0]
        for engines,speaks in (({'transcriber':FakeTranscriber(),'speaker':FakeSpeaker()},1),({},0)):
            wire=asyncio.run(ready(**engines))
            rows=self.run_commands([dict(op='ask'),self.receive(wire)])
            self.assertTrue(rows[1]['ok'],wire);self.assertEqual(rows[1]['speaks'],speaks)

    def transcript(self, status='heard', text='Is the fan louder?', key='session-q1', snr=12.5, **extra):
        return self.receive(self.envelope('transcript',question_id=key,status=status,text=text,
                                          speech_to_noise_db=snr,**extra))

    def asked(self, key='session-q1', **changes):
        meta,_=question(key,[0]*16000,**changes)
        return [dict(op='start_question'),dict(op='question_recorded',metadata=meta)]

    def test_spoken_question_confirm_retry_and_use(self):
        rows=self.run_commands(self.ready()+self.asked()+[self.transcript(),dict(op='start'),
            dict(op='confirm',accepted=False)]+self.asked('session-q2')+[
            self.transcript(key='session-q2',text='Is the fan louder near the wall?'),
            dict(op='confirm',accepted=True),dict(op='start')])
        self.assertEqual([r['state'] for r in rows[2:5]],['asking','transcribing','confirming'])
        self.assertEqual(rows[4]['transcript'],'Is the fan louder?')
        self.assertEqual(rows[4]['status'],'heard');self.assertEqual(rows[3]['status'],'')
        self.assertEqual(rows[4]['snr'],12.5)
        self.assertFalse(rows[5]['ok'])  # Record A needs Use or Retry first
        self.assertEqual(rows[6]['out']['type'],'question_confirm')
        self.assertEqual(rows[6]['out']['accepted'],False)
        self.assertEqual(rows[6]['question'],'')
        self.assertEqual(rows[6]['state'],'ready_a')
        self.assertEqual(rows[10]['out'],self.envelope('question_confirm',question_id='session-q2',accepted=True))
        self.assertEqual(rows[10]['question'],'Is the fan louder near the wall?')
        self.assertEqual(rows[10]['questions_left'],3)
        self.assertEqual(rows[11]['state'],'recording_a')

    def test_empty_or_failed_transcript_returns_to_record_a_without_confirm(self):
        for status in ('empty','failed'):
            with self.subTest(status=status):
                rows=self.run_commands(self.ready()+self.asked()+[self.transcript(status,'',snr=None),
                    dict(op='confirm',accepted=True),dict(op='start')])
                self.assertTrue(rows[4]['ok']);self.assertEqual(rows[4]['state'],'ready_a')
                self.assertEqual(rows[4]['status'],status)
                self.assertIsNone(rows[4]['snr'])
                self.assertFalse(rows[5]['ok']);self.assertEqual(rows[6]['state'],'recording_a')

    def test_hostile_transcripts_and_question_metadata_rejected(self):
        for patch in [dict(key='session-q9'),dict(status='heard',text=''),dict(status='empty',text='words'),
                      dict(status='other'),dict(text='x'*513),dict(snr='12'),dict(snr=True),
                      dict(extra=1),dict(text=' ')]:
            extra={'extra':1} if 'extra' in patch else {}
            args={k:v for k,v in patch.items() if k!='extra'}
            with self.subTest(patch=patch):
                rows=self.run_commands(self.ready()+self.asked()+[self.transcript(**args,**extra)])
                self.assertFalse(rows[-1]['ok']);self.assertEqual(rows[-1]['transcript'],'')
        wrong=self.envelope('transcript',question_id='session-q1',status='heard',text='x',speech_to_noise_db=1)
        wrong['session_id']='old'
        self.assertFalse(self.run_commands(self.ready()+self.asked()+[self.receive(wrong)])[-1]['ok'])
        for change in [dict(sample_rate_hz=48000),dict(channels=4),dict(frames=128001),dict(size_bytes=3),
                       dict(sha256='bad'),dict(session_id='old'),dict(driver_epoch_integrity=False),
                       dict(question_id='../x'),dict(acquisition_end_us=1000)]:
            with self.subTest(change=change):
                rows=self.run_commands(self.ready()+self.asked(**change))
                self.assertFalse(rows[-1]['ok'])

    def test_question_only_before_record_a_with_speech_available_and_bounded(self):
        rows=self.run_commands(self.ready(None)+[dict(op='start_question')])
        self.assertTrue(rows[1]['ok']);self.assertFalse(rows[2]['ok'])
        self.assertFalse(self.run_commands([dict(op='ask'),self.receive(self.envelope('ready',provider='x'))])[-1]['ok'])
        self.assertFalse(self.run_commands([dict(op='ask'),self.receive(self.envelope('ready',provider='x',speech_to_text=None))])[-1]['ok'])
        commands=self.ready()
        for n in range(1,6):
            commands+=self.asked(f'session-q{n}')+[self.transcript(key=f'session-q{n}'),dict(op='confirm',accepted=False)]
        rows=self.run_commands(commands+[dict(op='start_question')])
        self.assertEqual(rows[-2]['questions_left'],0);self.assertFalse(rows[-1]['ok'])
        prefix,_=self.prefix()
        self.assertFalse(self.run_commands(prefix+[dict(op='start_question')])[-1]['ok'])
        # Transcribing still has a deadline; cancel is local and final.
        rows=self.run_commands(self.ready()+self.asked()+[dict(op='tick',now=30100)])
        self.assertEqual(rows[-1]['state'],'incomplete')
        rows=self.run_commands(self.ready()+self.asked()+[dict(op='cancel'),self.transcript()])
        self.assertFalse(rows[-1]['ok']);self.assertEqual(rows[-1]['state'],'cancelled')

    def test_repeat_of_a_after_b_joins_the_comparison(self):
        commands,a=self.prefix()
        cap_b,b=self.capture('take-b',500,4000);cap_r,r=self.capture('take-r',900,7000)
        before_b=commands+[self.receive(self.reply([a])),dict(op='ack'),
            self.receive(self.envelope('acknowledged',request_id='r1',state='adjust')),
            dict(op='adjust'),dict(op='start'),cap_b]
        good=self.reply([a,b,r])
        rows=self.run_commands(before_b+[dict(op='await_repeat'),dict(op='uploaded'),dict(op='start'),cap_r,
            dict(op='await_repeat'),dict(op='uploaded'),self.receive(good),dict(op='ack'),
            self.receive(self.envelope('acknowledged',request_id='r2',state='complete'))])
        self.assertEqual(rows[11]['state'],'return_a')
        self.assertFalse(rows[12]['ok'])  # no compare turn while walking back to A
        self.assertEqual(rows[13]['state'],'recording_repeat')
        self.assertFalse(rows[15]['ok'])  # only one repeat
        self.assertEqual(rows[16]['out']['capture_ids'],['take-a','take-b','take-r'])
        self.assertEqual(rows[16]['out']['request_id'],'r2')
        self.assertEqual(rows[17]['state'],'acknowledging')
        self.assertEqual(rows[-1]['state'],'complete')
        # A repeat is only offered after B, and its comparison must carry the host's A-to-A value.
        early=self.run_commands(commands+[dict(op='await_repeat')])
        self.assertFalse(early[-1]['ok'])
        prefix=before_b+[dict(op='await_repeat'),dict(op='start'),cap_r,dict(op='uploaded')]
        for patch in [{'repeat_delta_db':0.0},{'repeat_delta_db':None},{'repeat_delta_db':'x'}]:
            with self.subTest(patch=patch):
                bad=copy.deepcopy(good);bad['comparison'].update(patch)
                self.assertFalse(self.run_commands(prefix+[self.receive(bad)])[-1]['ok'])
        bad=copy.deepcopy(good);del bad['comparison']['repeat_delta_db']
        self.assertFalse(self.run_commands(prefix+[self.receive(bad)])[-1]['ok'])
        bad=copy.deepcopy(good);bad['capture_ids']=['take-a','take-b']
        self.assertFalse(self.run_commands(prefix+[self.receive(bad)])[-1]['ok'])
        overlap,_=self.capture('take-r',900,4500)
        self.assertFalse(self.run_commands(before_b+[dict(op='await_repeat'),dict(op='start'),overlap])[-1]['ok'])

    def test_device_turns_are_accepted_by_the_host_service(self):
        # Join the two implementations: the reducer's own turn messages must pass the service.
        import asyncio,base64
        from tools.investigation_service import MockSession
        commands,a=self.prefix()
        cap_b,b=self.capture('take-b',500,4000);cap_r,r=self.capture('take-r',900,7000)
        rows=self.run_commands(commands+[self.receive(self.reply([a])),dict(op='ack'),
            self.receive(self.envelope('acknowledged',request_id='r1',state='adjust')),
            dict(op='adjust'),dict(op='start'),cap_b,dict(op='await_repeat'),dict(op='start'),cap_r,dict(op='uploaded')])
        turns=[rows[4]['out'],rows[-1]['out']]
        self.assertEqual(turns[1]['adjustment'],'Moved to 40 cm')
        async def run():
            sent=[]
            async def send(message):sent.append(message)
            with tempfile.TemporaryDirectory() as directory:
                service=MockSession(Path(directory),send)
                async def message(kind,**fields):
                    await service.receive(dict(version=1,type=kind,boot_id='boot',session_id='session',**fields))
                async def upload(key,amplitude,start):
                    meta,raw=evidence(key,amplitude,acquisition_start_us=start,acquisition_end_us=start+1000)
                    await message('capture_start',metadata=meta)
                    for offset in range(0,len(raw),4096):
                        await message('capture_chunk',capture_id=key,offset=offset,
                                      data=base64.b64encode(raw[offset:offset+4096]).decode())
                    await message('capture_end',capture_id=key,sha256=meta['sha256'])
                await message('hello',fixture=fixture().to_dict())
                await upload('take-a',1000,1000)
                await service.receive(turns[0]);await service.drain();await message('ack',request_id='r1')
                await upload('take-b',500,4000);await upload('take-r',900,7000)
                await service.receive(turns[1]);await service.drain()
                await service.close()
            return sent
        sent=asyncio.run(run())
        self.assertEqual(sent[-1]['type'],'comparison')
        self.assertIsNotNone(sent[-1]['comparison']['repeat_delta_db'])

    def test_complete_host_provider_exchange_and_ack_gate(self):
        commands,a=self.prefix()
        cap,b=self.capture('take-b',500,4000)
        commands += [self.receive(self.reply([a])),dict(op='start'),dict(op='ack'),
                     self.receive(self.envelope('acknowledged',request_id='r1',state='adjust')),
                     dict(op='adjust'),dict(op='start'),cap,dict(op='uploaded'),
                     self.receive(self.reply([a,b])),dict(op='ack'),
                     self.receive(self.envelope('acknowledged',request_id='r2',state='complete')),
                     dict(op='start')]
        rows=self.run_commands(commands)
        self.assertEqual(rows[4]['out']['capture_ids'],['take-a'])
        self.assertEqual(rows[5]['state'],'acknowledging')
        self.assertFalse(rows[6]['ok'])
        self.assertEqual(rows[-2]['state'],'complete')
        self.assertFalse(rows[-1]['ok'])
        self.assertEqual(rows[12]['out']['capture_ids'],['take-a','take-b'])

    def test_capture_snapshot_does_not_duplicate_large_ingress_proofs(self):
        commands,_=self.prefix()
        commands[3]['metadata']['ingress_blocks']=[
            dict(source_start_frame=i,frames=1,read_end_us=1001+i,sha256='a'*64)
            for i in range(141)]
        rows=self.run_commands(commands)
        self.assertTrue(rows[3]['ok'])
        self.assertLess(rows[3]['capture_allocated'],2048)
        # The command metadata is freed before turn(), so the ID must be owned.
        self.assertEqual(rows[4]['out']['capture_ids'],['take-a'])

    def test_wrong_identity_order_deadline_and_unbacked_values_rejected(self):
        prefix,a=self.prefix();good=self.reply([a])
        mutations=[{'session_id':'old'},{'boot_id':'old'},{'version':True},
                   {'request_id':'r2'},{'deadline_ms':15101},{'capture_ids':['missing']},
                   {'type':'comparison'},{'extra':1},{'text':'x'*2049}, {'text':''},
                   {'comparison':{'rms_delta_db':0}}, {'measurements':[]}]
        m=copy.deepcopy(good['measurements']);m[0]['rms_counts']=999
        mutations.append({'measurements':m})
        m=copy.deepcopy(good['measurements']);m[0]['median_dbfs']+=1
        mutations.append({'measurements':m})
        for patch in mutations:
            with self.subTest(patch=patch):
                rows=self.run_commands(prefix+[self.receive({**good,**patch})])
                self.assertFalse(rows[-1]['ok'])
                self.assertEqual(rows[-1]['text'],'')
        bad=json.dumps(good).replace('"version": 1','"version": 1, "version": 1')
        self.assertFalse(self.run_commands(prefix+[dict(op='receive',wire=bad)])[-1]['ok'])

    def test_cancel_disconnect_deadline_and_duplicate_cannot_advance(self):
        prefix,a=self.prefix();reply=self.receive(self.reply([a]))
        for action,state in [('cancel','cancelled'),('disconnect','offline'),('tick','incomplete')]:
            rows=self.run_commands(prefix+[dict(op=action,now=15100),reply,dict(op='start')])
            self.assertFalse(rows[-2]['ok']);self.assertFalse(rows[-1]['ok'])
            self.assertEqual(rows[-1]['state'],state)
        rows=self.run_commands(prefix+[reply,reply])
        self.assertFalse(rows[-1]['ok'])
        rows=self.run_commands(prefix+[self.receive(self.reply([a]),15100)])
        self.assertFalse(rows[-1]['ok']);self.assertEqual(rows[-1]['state'],'incomplete')

    def test_capture_settings_integrity_and_extent_are_guarded(self):
        prefix,_=self.prefix()
        for patch in [{'session_id':'old'},{'frames':5},{'source_slot':1},
                      {'driver_epoch_integrity':False},{'speaker_active':True},
                      {'size_bytes':1},{'sha256':'bad'},{'acquisition_end_us':1000}]:
            cmd=copy.deepcopy(prefix[3]);cmd['metadata'].update(patch)
            self.assertFalse(self.run_commands(prefix[:3]+[cmd])[-1]['ok'])
        rows=self.run_commands(prefix[:3]+[dict(op='cancel'),prefix[3]])
        self.assertFalse(rows[-1]['ok'])

    def test_waits_expire_without_reply_and_terminal_result_survives_disconnect(self):
        rows=self.run_commands([dict(op='ask'),dict(op='tick',now=15100)])
        self.assertEqual(rows[-1]['state'],'incomplete')

    def test_ack_must_be_sent_once_and_acknowledged_before_b(self):
        prefix,a=self.prefix();reply=self.receive(self.reply([a]))
        acknowledged=self.receive(self.envelope('acknowledged',request_id='r1',state='adjust'))
        rows=self.run_commands(prefix+[reply,acknowledged,dict(op='ack'),dict(op='ack'),acknowledged])
        self.assertFalse(rows[-4]['ok']);self.assertTrue(rows[-3]['ok'])
        self.assertFalse(rows[-2]['ok']);self.assertEqual(rows[-1]['state'],'adjust')

    def test_duplicate_capture_and_overlap_rejected_after_a(self):
        prefix,a=self.prefix()
        prefix += [self.receive(self.reply([a])),dict(op='ack'),
                   self.receive(self.envelope('acknowledged',request_id='r1',state='adjust')),
                   dict(op='adjust'),dict(op='start')]
        for key,start in [('take-a',4000),('take-b',1500)]:
            cap,_=self.capture(key,500,start)
            self.assertFalse(self.run_commands(prefix+[cap])[-1]['ok'])

    def test_nul_trailing_json_oversized_and_nonfinite_rejected(self):
        prefix,a=self.prefix();wire=json.dumps(self.reply([a]))
        for bad in [wire+'{}',wire.replace('"session"','"session\\u0000old"'),
                    wire.replace('1000.0','1e999'),wire+' '*32768]:
            self.assertFalse(self.run_commands(prefix+[dict(op='receive',wire=bad)])[-1]['ok'])
