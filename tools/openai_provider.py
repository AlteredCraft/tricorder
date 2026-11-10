"""OpenAI-compatible prose over a checked analysis (the service checks the reply, ADR-0012).

Routes: openai, openrouter, or local (an OpenAI-compatible server on the Mac such as
Ollama, which answers the Responses API; F-0003). Only openrouter gets vendor routing extras.
"""
import asyncio
import base64
import json

from tools.service_protocol import ProtocolError, bounded_text, require


class OpenAIProvider:
    name = 'openai-responses-v1'

    def __init__(self, client, *, model='gpt-4.1-mini', route='openai'):
        require(route in ('openai', 'openrouter', 'local'), 'unknown API route')
        self.client = client
        self.model = bounded_text(model, 96)
        self.route = route
        self.name = f'{route}-responses-v1'

    def routing(self):
        """Per-route request extras. Reasoning off: the prose needs no thinking, and a local
        model otherwise spends the whole token budget thinking (`20261103-local-explain-smoke`)."""
        if self.route == 'openrouter':
            return {'extra_body': {'provider': {'require_parameters': True}}, 'reasoning': {'effort': 'none'}}
        if self.route == 'local':
            return {'reasoning': {'effort': 'none'}}
        return {}

    async def explain(self, evidence):
        """F-0002, F-0005, F-0006, F-0007: plain prose over a checked sound, motion or power analysis
        summary, or over a photo (the JPEG goes as an image input beside the question)."""
        from tools import camera_explain, motion_explain, power_explain, sound_explain
        kind = evidence.get('kind', 'sound')
        module = {'motion': motion_explain, 'camera': camera_explain, 'power': power_explain}.get(kind, sound_explain)
        schema = {'type': 'object', 'additionalProperties': False,
                  'properties': {'text': {'type': 'string'}}, 'required': ['text']}
        if kind == 'camera':
            text = {key: value for key, value in evidence.items() if key != 'image_jpeg'}
            image = base64.b64encode(evidence['image_jpeg']).decode()
            content = [{'type': 'input_text', 'text': json.dumps(text, allow_nan=False)},
                       {'type': 'input_image', 'image_url': f'data:image/jpeg;base64,{image}'}]
        else:
            content = json.dumps(evidence, allow_nan=False)
        try:
            routing = self.routing()
            response = await self.client.responses.create(
                model=self.model, store=False, max_output_tokens=700, instructions=module.INSTRUCTIONS,
                input=[{'role': 'user', 'content': content}],
                text={'format': {'type': 'json_schema', 'name': f'{kind}_analysis_reading',
                                 'strict': True, 'schema': schema}}, **routing)
            require(response.status == 'completed', 'OpenAI response incomplete')
            wire = response.output_text
            require(isinstance(wire, str) and len(wire.encode()) <= 8192, 'OpenAI response outside bounds')
            output = json.loads(wire)
            require(isinstance(output, dict) and set(output) == {'text'} and isinstance(output['text'], str),
                    'OpenAI response fields')
            return output['text']
        except asyncio.CancelledError:
            raise
        except Exception:
            raise ProtocolError('OpenAI request failed') from None  # SDK errors can carry credentials
