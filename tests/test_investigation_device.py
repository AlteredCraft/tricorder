"""Run the firmware protocol against host-generated replies, including hostile ones."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from tools.investigation import CaptureEvidence, MockProvider
from test_investigation import evidence, fixture


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
int main() {
 InvestigationProtocol p("boot", "session", 960);
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
  } else if(action=="start") ok=p.start_capture();
  else if(action=="captured") {
   auto* m=cJSON_GetObjectItemCaseSensitive(cmd,"metadata");
   auto* v=cJSON_GetObjectItemCaseSensitive(cmd,"measurement");
   ok=p.captured(m,v,t);
  } else if(action=="uploaded") {out=p.turn(t);ok=out;}
  else if(action=="adjust") ok=p.adjust("Moved to 40 cm");
  else if(action=="cancel") {p.cancel();ok=true;}
  else if(action=="disconnect") {p.disconnect();ok=true;}
  else if(action=="tick") {p.tick(t);ok=true;}
  else if(action=="ack") {out=p.ack();ok=out;}
  auto* result=cJSON_CreateObject();
  cJSON_AddBoolToObject(result,"ok",ok);
  cJSON_AddStringToObject(result,"state",p.state_name());
  cJSON_AddStringToObject(result,"text",p.text());
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
        return [dict(op='ask'),self.receive(self.envelope('ready',provider='scripted-mock-v1')),
                dict(op='start'),capture,dict(op='uploaded')],item

    def reply(self, items, deadline=15100):
        request=self.envelope('guide' if len(items)==1 else 'compare',request_id=f'r{len(items)}',
                              deadline_ms=deadline,fixture=fixture().to_dict(),
                              captures=[x.to_dict() for x in items],adjustment='Moved to 40 cm')
        return MockProvider().respond(request)

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

    def test_wrong_identity_order_deadline_and_unbacked_values_rejected(self):
        prefix,a=self.prefix();good=self.reply([a])
        mutations=[{'session_id':'old'},{'boot_id':'old'},{'version':True},
                   {'request_id':'r2'},{'deadline_ms':15101},{'capture_ids':['missing']},
                   {'type':'comparison'},{'extra':1},{'text':'x'*2049}, {'text':''},
                   {'comparison':{'rms_delta_db':0}}, {'measurements':[]}]
        m=copy.deepcopy(good['measurements']);m[0]['rms_counts']=999
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
