"""An independent assessor must reject broken evidence joins in saved mock runs."""
import asyncio
import base64
import json
from pathlib import Path
import tempfile
import unittest
from tools.investigation_service import MockSession
from test_investigation import evidence, fixture
from tools.investigation_evidence import assess_run

class InvestigationEvidenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        async def send(_):pass
        s=MockSession(self.root,send)
        async def message(kind,**fields):
            await s.receive(dict(version=1,type=kind,boot_id='boot',session_id='session',**fields))
        await message('hello',fixture=fixture().to_dict())
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

    async def test_corrupt_bytes_or_reply_cannot_pass(self):
        capture=next((self.run/'captures').glob('*.bin'));capture.write_bytes(b'bad')
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
