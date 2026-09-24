import asyncio
import copy
import json
from types import SimpleNamespace
import unittest

from tools.investigation import CaptureEvidence, ProtocolError, validate_reply
from tools.openai_provider import OpenAIProvider
from test_investigation import evidence, fixture


class OpenAIProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_openrouter_preserves_exact_model_and_required_parameters(self):
        provider=self.provider(dict(text='Use the recorded evidence.',capture_ids=['take-0']))
        provider=OpenAIProvider(provider.client,route='openrouter',model='openai/gpt-5.6-sol')
        reply=await provider.respond(self.request())
        validate_reply(self.request(),reply)
        self.assertEqual(provider.name,'openrouter-responses-v1')
        self.assertEqual(self.calls[0]['model'],'openai/gpt-5.6-sol')
        self.assertTrue(self.calls[0]['extra_body']['provider']['require_parameters'])
        self.assertFalse(self.calls[0]['store'])

    def request(self, pair=False):
        captures=[]
        for index in range(2 if pair else 1):
            meta,raw=evidence(f'take-{index}',1000//(index+1),
                              acquisition_start_us=100+index*30000,
                              acquisition_end_us=20100+index*30000)
            captures.append(CaptureEvidence.from_pcm(meta,raw).to_dict())
        return dict(version=1,type='compare' if pair else 'guide',boot_id='boot',
                    session_id='session',request_id='r2' if pair else 'r1',
                    deadline_ms=15100,fixture=fixture().to_dict(),captures=captures,
                    adjustment='Moved to B' if pair else None)

    def provider(self, content=None, status='completed'):
        self.calls=[]
        async def create(**kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(status=status,output_text=json.dumps(content))
        return OpenAIProvider(SimpleNamespace(responses=SimpleNamespace(create=create)),
                              model='test-model')

    async def test_live_text_uses_verified_host_values_and_same_contract(self):
        for pair in (False,True):
            request=self.request(pair)
            original=copy.deepcopy(request)
            ids=[c['capture_id'] for c in request['captures']]
            provider=self.provider(dict(text='Compare these retained recordings.',capture_ids=ids))
            reply=await provider.respond(request)
            validate_reply(request,reply)
            self.assertEqual(reply['text'],'Compare these retained recordings.')
            self.assertEqual(request,original)
            self.assertEqual(reply['measurements'],[c['measurement'] for c in request['captures']])
            sent=self.calls[-1]
            self.assertFalse(sent['store'])
            self.assertTrue(sent['text']['format']['strict'])
            payload=json.loads(sent['input'][0]['content'])
            self.assertEqual(payload['captures'],request['captures'])
            self.assertNotIn('raw',payload)
            self.assertNotIn('metadata',payload)

    async def test_reject_unknown_reordered_missing_references_and_unbacked_fields(self):
        request=self.request(True)
        for output in (
            dict(text='ok',capture_ids=['invented']),
            dict(text='ok',capture_ids=['take-1','take-0']),
            dict(text='ok'),
            dict(text='ok',capture_ids=['take-0','take-1'],measurements=[123]),
            dict(text='é'*1100,capture_ids=['take-0','take-1']),
            dict(text=' ',capture_ids=['take-0','take-1'])):
            with self.subTest(output=str(output)[:80]),self.assertRaises(ProtocolError):
                await self.provider(output).respond(request)

    async def test_prose_numbers_with_measurement_units_must_match_host_values(self):
        # Pair: A 1000 counts (-30.31 dBFS), B 500 counts; B/A = -6.0206 dB; gain 24 dB; 48000 Hz.
        request=self.request(True)
        ids=['take-0','take-1']
        backed=('B is 6.02 dB quieter than A.','B is about 6 dB lower.','B/A was −6.0 dB.',
                'A read -30.3 dBFS.','Gain stayed at 24 dB.','Recorded at 48 kHz.',
                'Move 16 inches closer and repeat.','A had 1000 counts RMS.')
        for text in backed:
            with self.subTest(text=text):
                reply=await self.provider(dict(text=text,capture_ids=ids)).respond(request)
                self.assertEqual(reply['text'],text)
        for text in ('B is 1.7 dB quieter.','A read -40 dBFS.','A 3 dB change is barely audible.',
                     'The peak is near 5000 Hz.','B had 900 counts RMS.','B is 6.5 dB quieter.'):
            with self.subTest(text=text),self.assertRaises(ProtocolError):
                await self.provider(dict(text=text,capture_ids=ids)).respond(request)
        self.assertIn('only as given',self.calls[-1]['instructions'])

    async def test_incomplete_refusal_and_provider_error_never_fall_back_to_mock(self):
        for status in ('incomplete','failed'):
            with self.assertRaises(ProtocolError):
                await self.provider(dict(text='partial',capture_ids=['take-0']),status).respond(self.request())
        provider=self.provider()
        async def fail(**_):raise RuntimeError('secret-key-must-not-escape')
        provider.client.responses.create=fail
        with self.assertRaisesRegex(ProtocolError,'OpenAI request failed') as caught:
            await provider.respond(self.request())
        self.assertNotIn('secret',str(caught.exception))

    async def test_cancellation_propagates_to_inflight_api_call(self):
        provider=self.provider()
        entered=asyncio.Event();cancelled=asyncio.Event()
        async def wait(**_):
            entered.set()
            try:await asyncio.Event().wait()
            finally:cancelled.set()
        provider.client.responses.create=wait
        task=asyncio.create_task(provider.respond(self.request()))
        await asyncio.wait_for(entered.wait(),1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertTrue(cancelled.is_set())

    async def test_invalid_evidence_is_rejected_before_api_call(self):
        provider=self.provider()
        request=self.request();request['captures'][0]['boot_id']='other'
        with self.assertRaises(ProtocolError):await provider.respond(request)
        self.assertEqual(self.calls,[])
