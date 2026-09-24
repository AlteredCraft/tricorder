"""An independent assessor must reject broken evidence joins in saved mock runs."""
import asyncio
import base64
import json
from pathlib import Path
import tempfile
import unittest
from tools.investigation_service import MockSession
from test_investigation import evidence, fixture
from test_question import question
from test_spoken_ask_service import FakeTranscriber
from tools.investigation_evidence import assess_run

class InvestigationEvidenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        async def send(_):pass
        s=MockSession(self.root,send,transcriber=FakeTranscriber('Is it louder?','Is the fan louder?'))
        async def message(kind,**fields):
            await s.receive(dict(version=1,type=kind,boot_id='boot',session_id='session',**fields))
        await message('hello',fixture=fixture().to_dict())
        for n,accepted in ((1,False),(2,True)):
            key=f'session-q{n}';meta,raw=question(key)
            await message('question_start',metadata=meta)
            for offset in range(0,len(raw),4096):
                await message('question_chunk',question_id=key,offset=offset,data=base64.b64encode(raw[offset:offset+4096]).decode())
            await message('question_end',question_id=key,sha256=meta['sha256'])
            await s.drain();await message('question_confirm',question_id=key,accepted=accepted)
        for index,amplitude in enumerate([1000,500]):
            key=f'take-{index}';meta,raw=evidence(key,amplitude,acquisition_start_us=index*30000+100,acquisition_end_us=index*30000+20100)
            await message('capture_start',metadata=meta)
            for offset in range(0,len(raw),4096):
                await message('capture_chunk',capture_id=key,offset=offset,data=base64.b64encode(raw[offset:offset+4096]).decode())
            await message('capture_end',capture_id=key,sha256=meta['sha256'])
            fields={'adjustment':'Moved to 40 cm'} if index else {}
            await message('turn',request_id=f'r{index+1}',capture_ids=[f'take-{i}' for i in range(index+1)],
                          device_ms=100000+index*30000,deadline_ms=115000+index*30000,**fields)
            await s.drain();await message('ack',request_id=f'r{index+1}')
        await s.close();self.run=self.root/'boot-session'

    async def test_complete_pair_recomputed_from_saved_raw(self):
        result=assess_run(self.run)
        self.assertEqual(result['status'],'pass',result)
        self.assertAlmostEqual(result['rms_delta_db'],-6.020599913)
        self.assertFalse(result['driver_proofs_present'])
        self.assertEqual(result['operator_question'],'Is the fan louder?')
        self.assertEqual([q['status'] for q in result['questions']],['heard','heard'])
        self.assertEqual([q['accepted'] for q in result['questions']],[False,True])
        self.assertAlmostEqual(result['questions'][0]['speech_to_noise_db'],15,delta=1)

    async def test_question_audio_must_match_its_transcript_record(self):
        (self.run/'questions'/'session-q2.bin').write_bytes(b'bad')
        self.assertEqual(assess_run(self.run)['status'],'fail')

    async def test_question_traffic_after_capture_a_is_rejected(self):
        path=self.run/'transcript.jsonl'
        rows=[json.loads(line) for line in path.read_text().splitlines()]
        moved=[r for r in rows if r['message'].get('payload',{}).get('type','').startswith('question_confirm')]
        rows=[r for r in rows if r not in moved]
        at=next(i for i,r in enumerate(rows) if r['message'].get('payload',{}).get('type')=='turn')
        rows[at:at]=moved
        path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
        self.assertEqual(assess_run(self.run)['status'],'fail')

    async def test_corrupt_bytes_or_reply_cannot_pass(self):
        capture=next((self.run/'captures').glob('*.bin'));capture.write_bytes(b'bad')
        self.assertEqual(assess_run(self.run)['status'],'fail')

    async def test_replay_label_must_match_hello_and_survive_assessment(self):
        manifest=self.run/'manifest.json';value=json.loads(manifest.read_text())
        value['replay']=True;manifest.write_text(json.dumps(value))
        self.assertEqual(assess_run(self.run)['status'],'fail')
        path=self.run/'transcript.jsonl';rows=[json.loads(line) for line in path.read_text().splitlines()]
        rows[0]['message']['payload']['replay']=True
        path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
        result=assess_run(self.run)
        self.assertEqual(result['status'],'pass',result)
        self.assertTrue(result['replay'])
        self.assertIn('no new sensor acquisition',result['scope'])
        value.pop('replay');manifest.write_text(json.dumps(value))
        self.assertEqual(assess_run(self.run)['status'],'fail')

    async def test_wrong_reply_measurement_and_missing_ack_rejected(self):
        path=self.run/'transcript.jsonl'
        original=path.read_text()
        rows=[json.loads(line) for line in original.splitlines()]
        for row in rows:
            payload=row['message'].get('payload',{})
            if payload.get('type')=='comparison':payload['measurements'][0]['rms_counts']=123
        path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
        result=assess_run(self.run)
        self.assertEqual(result['status'],'fail')
        self.assertIn('unbacked rms_counts',result['errors'])
        rows=[json.loads(line) for line in original.splitlines()]
        rows=[row for row in rows if not (row['message'].get('payload',{}).get('type')=='acknowledged'
                                         and row['message']['payload'].get('state')=='complete')]
        path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
        self.assertEqual(assess_run(self.run)['status'],'fail')
