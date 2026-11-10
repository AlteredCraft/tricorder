import asyncio
import base64
import json
from types import SimpleNamespace
import unittest

from tools import camera_explain, sound_explain
from tools.openai_provider import OpenAIProvider
from tools.service_protocol import ProtocolError
from test_service import summary


class OpenAIProviderTests(unittest.IsolatedAsyncioTestCase):
    def provider(self, content=None, status='completed', **options):
        self.calls=[]
        async def create(**kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(status=status,output_text=json.dumps(content or dict(text='A quiet room.')))
        return OpenAIProvider(SimpleNamespace(responses=SimpleNamespace(create=create)),**options)

    def evidence(self, note=None):
        return sound_explain.explain_evidence(sound_explain.validate_analysis(summary()),note)

    async def test_openrouter_preserves_exact_model_and_required_parameters(self):
        provider=self.provider(route='openrouter',model='openai/gpt-5.6-sol')
        self.assertEqual(await provider.explain(self.evidence()),'A quiet room.')
        self.assertEqual(provider.name,'openrouter-responses-v1')
        self.assertEqual(self.calls[0]['model'],'openai/gpt-5.6-sol')
        self.assertTrue(self.calls[0]['extra_body']['provider']['require_parameters'])
        self.assertFalse(self.calls[0]['store'])

    async def test_local_route_sends_no_vendor_routing_and_names_itself(self):
        provider=self.provider(route='local',model='gemma4:latest')
        await provider.explain(self.evidence())
        self.assertEqual(provider.name,'local-responses-v1')
        self.assertEqual(self.calls[0]['model'],'gemma4:latest')
        self.assertNotIn('extra_body',self.calls[0])
        self.assertEqual(self.calls[0]['reasoning'],{'effort':'none'})
        with self.assertRaises(ProtocolError):OpenAIProvider(provider.client,route='ollama')

    async def test_sound_analysis_goes_as_json_with_the_sound_prompt(self):
        evidence=self.evidence('The grinder started near the end.')
        await self.provider().explain(evidence)
        sent=self.calls[0]
        self.assertEqual(sent['instructions'],sound_explain.INSTRUCTIONS)
        self.assertTrue(sent['text']['format']['strict'])
        self.assertEqual(sent['text']['format']['name'],'sound_analysis_reading')
        self.assertEqual(json.loads(sent['input'][0]['content']),json.loads(json.dumps(evidence)))

    async def test_photo_goes_as_an_image_beside_the_question(self):
        photo=b'\xff\xd8fake-jpeg\xff\xd9'
        await self.provider().explain({'kind':'camera','question':'What is this?','image_jpeg':photo})
        sent=self.calls[0]
        self.assertEqual(sent['instructions'],camera_explain.INSTRUCTIONS)
        text,image=sent['input'][0]['content']
        self.assertEqual(json.loads(text['text']),{'kind':'camera','question':'What is this?'})
        self.assertEqual(image,{'type':'input_image',
                                'image_url':'data:image/jpeg;base64,'+base64.b64encode(photo).decode()})

    async def test_incomplete_malformed_and_failed_calls_raise_without_leaking(self):
        for status in ('incomplete','failed'):
            with self.assertRaises(ProtocolError):
                await self.provider(status=status).explain(self.evidence())
        for content in (dict(text='ok',extra=1),dict(text=7),['ok']):
            with self.subTest(content=content),self.assertRaises(ProtocolError):
                await self.provider(content).explain(self.evidence())
        provider=self.provider()
        async def fail(**_):raise RuntimeError('secret-key-must-not-escape')
        provider.client.responses.create=fail
        with self.assertRaisesRegex(ProtocolError,'OpenAI request failed') as caught:
            await provider.explain(self.evidence())
        self.assertNotIn('secret',str(caught.exception))

    async def test_cancellation_propagates_to_inflight_api_call(self):
        provider=self.provider()
        entered=asyncio.Event();cancelled=asyncio.Event()
        async def wait(**_):
            entered.set()
            try:await asyncio.Event().wait()
            finally:cancelled.set()
        provider.client.responses.create=wait
        task=asyncio.create_task(provider.explain(self.evidence()))
        await asyncio.wait_for(entered.wait(),1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertTrue(cancelled.is_set())


if __name__=='__main__':unittest.main()
