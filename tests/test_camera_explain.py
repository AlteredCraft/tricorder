"""F-0006: the agent explains a photo taken on the device."""
import base64
import hashlib
from pathlib import Path
import tempfile
import unittest

from tools.camera_explain import (CHUNK_BYTES, QUESTION, check_photo, checked_text, explain_evidence,
                                  validate_analysis)
from tools.investigation import ProtocolError
from tools.investigation_service import MockSession
from test_investigation import fixture
from test_sound_explain import RecordingExplainer
import test_spoken_ask_service as spoken
from test_spoken_guidance import FakeSpeaker

PHOTO = b'\xff\xd8\xff\xe0' + bytes(range(256))*40


def summary(photo=PHOTO, **changes):
    value = {'kind': 'camera', 'format': 'jpeg', 'width': 1280, 'height': 720, 'size_bytes': len(photo),
             'sha256': hashlib.sha256(photo).hexdigest()}
    value.update(changes)
    return value


class CameraExplainTests(unittest.TestCase):
    def test_analysis_and_photo_are_checked(self):
        analysis = validate_analysis(summary())
        check_photo(analysis, PHOTO)
        for bad in (summary(kind='photo'), summary(format='png'), summary(width=0), summary(sha256='abc'),
                    summary(extra=1), summary(size_bytes=10**7)):
            with self.assertRaises(ProtocolError):
                validate_analysis(bad)
        with self.assertRaises(ProtocolError):
            check_photo(analysis, PHOTO[:-1])
        with self.assertRaises(ProtocolError):
            check_photo(validate_analysis(summary(b'abcd')), b'abcd')

    def test_evidence_and_text_check(self):
        evidence = explain_evidence(validate_analysis(summary()), PHOTO)
        self.assertEqual(evidence['question'], QUESTION)
        self.assertEqual(evidence['image_jpeg'], PHOTO)
        self.assertEqual(checked_text('A blue mug on a desk, about 90% full.', evidence),
                         'A blue mug on a desk, about 90% full.')
        with self.assertRaises(ProtocolError):
            checked_text('   ', evidence)


class CameraExplainServiceTests(unittest.IsolatedAsyncioTestCase):
    send = spoken.SpokenAskServiceTests.send
    asyncTearDown = spoken.SpokenAskServiceTests.asyncTearDown

    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.provider = RecordingExplainer()
        self.sent = []
        async def send(message): self.sent.append(message)
        self.service = MockSession(self.root / 'run', send, provider=self.provider,
                                   transcriber=spoken.FakeTranscriber('unused'), speaker=FakeSpeaker(seconds=0.2))
        await self.send('hello', fixture=fixture().to_dict())

    async def upload(self, photo=PHOTO, request_id='explain-1'):
        for offset in range(0, len(photo), CHUNK_BYTES):
            await self.send('photo_chunk', request_id=request_id, offset=offset,
                            data=base64.b64encode(photo[offset:offset+CHUNK_BYTES]).decode())

    async def explain(self, value):
        await self.send('analysis_explain', request_id='explain-1', analysis=value)
        await self.service.drain()
        return self.sent[-1]

    async def test_explains_a_photo_and_keeps_it(self):
        await self.upload()
        reply = await self.explain(summary())
        self.assertEqual(reply['type'], 'analysis_reply')
        self.assertIn('1280 by 720', reply['text'])
        evidence = self.provider.evidence[0]
        self.assertEqual(evidence['kind'], 'camera')
        self.assertEqual(evidence['image_jpeg'], PHOTO)
        self.assertEqual((self.service.archive.root / 'photos' / 'explain-1.jpg').read_bytes(), PHOTO)
        transcript = (self.service.archive.root / 'transcript.jsonl').read_text()
        self.assertNotIn(base64.b64encode(PHOTO[:CHUNK_BYTES]).decode()[:40], transcript)

    async def test_chunks_arrive_in_order_for_one_request(self):
        await self.upload(PHOTO[:CHUNK_BYTES])
        with self.assertRaises(ProtocolError):
            await self.send('photo_chunk', request_id='explain-1', offset=0,
                            data=base64.b64encode(PHOTO[:10]).decode())
        with self.assertRaises(ProtocolError):
            await self.send('photo_chunk', request_id='explain-2', offset=0,
                            data=base64.b64encode(PHOTO[:10]).decode())

    async def test_photo_must_match_its_analysis(self):
        await self.upload(PHOTO[:-1])
        with self.assertRaises(ProtocolError):
            await self.send('analysis_explain', request_id='explain-1', analysis=summary())

    async def test_camera_explain_without_photo_is_rejected(self):
        with self.assertRaises(ProtocolError):
            await self.send('analysis_explain', request_id='explain-1', analysis=summary())


if __name__ == '__main__':
    unittest.main()
