"""Run the firmware protocol against host-generated replies, including hostile ones."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_question import question


class DeviceProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        root = Path(cls.temp.name)
        source = root/'driver.cpp'
        source.write_text(r'''
#include "service_protocol.h"
#include <iostream>
#include <string>
#include <cstdlib>
#include <cmath>
int main() {
 ServiceProtocol p("boot", "session");
 std::string line;
 while(std::getline(std::cin,line)) {
  auto* cmd=cJSON_Parse(line.c_str());
  auto* op=cJSON_GetObjectItemCaseSensitive(cmd,"op");
  auto* now=cJSON_GetObjectItemCaseSensitive(cmd,"now");
  uint64_t t=now?static_cast<uint64_t>(now->valuedouble):100;
  bool ok=false; cJSON* out=nullptr;
  std::string action=op->valuestring;
  if(action=="ask") {ok=p.ask(t);}
  else if(action=="receive") {
   auto* wire=cJSON_GetObjectItemCaseSensitive(cmd,"wire");
   ok=p.receive(wire->valuestring,t);
  } else if(action=="disconnect") {p.disconnect();ok=true;}
  else if(action=="tick") {p.tick(t);ok=true;}
  else if(action=="start_question") ok=p.start_question();
  else if(action=="question_recorded") {
   ok=p.question_recorded(cJSON_GetObjectItemCaseSensitive(cmd,"metadata"),t);
  } else if(action=="confirm") {
   out=p.confirm_question(cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(cmd,"accepted")));ok=out;
  }
  auto* result=cJSON_CreateObject();
  cJSON_AddBoolToObject(result,"ok",ok);
  cJSON_AddStringToObject(result,"state",p.state_name());
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
                                 str(source),'firmware/main/service_protocol.cpp',
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

    def ready(self, speech='fake-stt', voice='fake-tts'):
        return [dict(op='ask'),self.receive(self.envelope('ready',provider='scripted-mock-v1',speech_to_text=speech,
                                                              speech_output=voice))]

    def test_service_ready_is_accepted_and_names_speech_output(self):
        import asyncio
        from tools.service import Session
        from test_service import FakeSpeaker, FakeTranscriber
        async def ready(**engines):
            sent=[]
            async def send(message):sent.append(message)
            with tempfile.TemporaryDirectory() as directory:
                service=Session(Path(directory),send,**engines)
                await service.receive(dict(version=1,type='hello',boot_id='boot',session_id='session'))
                await service.close()
            return sent[0]
        for engines,speaks in (({'transcriber':FakeTranscriber(),'speaker':FakeSpeaker()},1),({},0)):
            wire=asyncio.run(ready(**engines))
            rows=self.run_commands([dict(op='ask'),self.receive(wire)])
            self.assertTrue(rows[1]['ok'],wire);self.assertEqual(rows[1]['speaks'],speaks)
            self.assertEqual(rows[1]['state'],'ready')

    def transcript(self, status='heard', text='Is the fan louder?', key='session-q1', snr=12.5, **extra):
        return self.receive(self.envelope('transcript',question_id=key,status=status,text=text,
                                          speech_to_noise_db=snr,**extra))

    def asked(self, key='session-q1', **changes):
        meta,_=question(key,[0]*16000,**changes)
        return [dict(op='start_question'),dict(op='question_recorded',metadata=meta)]

    def test_voice_note_is_transcribed_then_confirmed(self):
        rows=self.run_commands(self.ready()+self.asked()+[self.transcript(),dict(op='start_question'),
            dict(op='confirm',accepted=False)]+self.asked('session-q2')+[
            self.transcript(key='session-q2',text='Is the fan louder near the wall?'),
            dict(op='confirm',accepted=True)])
        self.assertEqual([r['state'] for r in rows[2:5]],['asking','transcribing','confirming'])
        self.assertEqual(rows[4]['transcript'],'Is the fan louder?')
        self.assertEqual(rows[4]['status'],'heard');self.assertEqual(rows[3]['status'],'')
        self.assertEqual(rows[4]['snr'],12.5)
        self.assertFalse(rows[5]['ok'])  # a heard transcript must be confirmed first
        self.assertEqual(rows[6]['out']['type'],'question_confirm')
        self.assertEqual(rows[6]['out']['accepted'],False)
        self.assertEqual(rows[6]['state'],'ready')
        self.assertEqual(rows[10]['out'],self.envelope('question_confirm',question_id='session-q2',accepted=True))
        self.assertEqual(rows[10]['questions_left'],3)
        self.assertEqual(rows[10]['state'],'ready')

    def test_empty_or_failed_transcript_returns_to_ready_without_confirm(self):
        for status in ('empty','failed'):
            with self.subTest(status=status):
                rows=self.run_commands(self.ready()+self.asked()+[self.transcript(status,'',snr=None),
                    dict(op='confirm',accepted=True)])
                self.assertTrue(rows[4]['ok']);self.assertEqual(rows[4]['state'],'ready')
                self.assertEqual(rows[4]['status'],status)
                self.assertIsNone(rows[4]['snr'])
                self.assertFalse(rows[5]['ok'])

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

    def test_voice_note_needs_speech_to_text_and_is_bounded(self):
        rows=self.run_commands(self.ready(None)+[dict(op='start_question')])
        self.assertTrue(rows[1]['ok']);self.assertFalse(rows[2]['ok'])
        self.assertFalse(self.run_commands([dict(op='ask'),self.receive(self.envelope('ready',provider='x'))])[-1]['ok'])
        self.assertFalse(self.run_commands([dict(op='ask'),self.receive(self.envelope('ready',provider='x',speech_to_text=None))])[-1]['ok'])
        commands=self.ready()
        for n in range(1,6):
            commands+=self.asked(f'session-q{n}')+[self.transcript(key=f'session-q{n}'),dict(op='confirm',accepted=False)]
        rows=self.run_commands(commands+[dict(op='start_question')])
        self.assertEqual(rows[-2]['questions_left'],0);self.assertFalse(rows[-1]['ok'])
        # Transcribing has a deadline; a dropped connection is final.
        rows=self.run_commands(self.ready()+self.asked()+[dict(op='tick',now=30100)])
        self.assertEqual(rows[-1]['state'],'incomplete')
        rows=self.run_commands(self.ready()+self.asked()+[dict(op='disconnect'),self.transcript()])
        self.assertFalse(rows[-1]['ok']);self.assertEqual(rows[-1]['state'],'offline')

    def test_ready_must_arrive_in_time_and_only_once(self):
        ready=self.envelope('ready',provider='scripted-mock-v1',speech_to_text=None,speech_output=None)
        rows=self.run_commands([dict(op='ask'),self.receive(ready,now=15100)])
        self.assertFalse(rows[-1]['ok']);self.assertEqual(rows[-1]['state'],'incomplete')
        rows=self.run_commands([dict(op='ask'),self.receive(ready),self.receive(ready)])
        self.assertTrue(rows[1]['ok']);self.assertFalse(rows[2]['ok'])
        self.assertFalse(self.run_commands([self.receive(ready)])[-1]['ok'])  # before hello

    def test_nul_trailing_json_oversized_and_nonfinite_rejected(self):
        wire=json.dumps(self.envelope('transcript',question_id='session-q1',status='heard',text='Is it louder?',
                                      speech_to_noise_db=12.5))
        prefix=self.ready()+self.asked()
        self.assertTrue(self.run_commands(prefix+[dict(op='receive',wire=wire)])[-1]['ok'])
        for bad in [wire+'{}',wire.replace('"session"','"session\\u0000old"'),
                    wire.replace('12.5','1e999'),wire+' '*32768]:
            self.assertFalse(self.run_commands(prefix+[dict(op='receive',wire=bad)])[-1]['ok'])
