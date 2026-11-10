"""F-0002 T5: the agent explains an on-device sound analysis, steered by a voice note."""
import asyncio
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from tools.service import Session
from tools.service_protocol import ProtocolError
from tools.sound_explain import explain_evidence, validate_analysis
import test_service as spoken
from test_service import FakeSpeaker, RecordingExplainer, summary


class ValidateAnalysisTests(unittest.TestCase):
    def test_accepts_a_device_summary(self):
        self.assertEqual(validate_analysis(summary())['event_count'], 1)

    def test_rejects_malformed_summaries(self):
        bad = [
            summary(extra=1),
            summary(background_db=float('nan')),
            summary(duration_s=0),
            summary(event_count=-1),
            summary(event_count=True),
            summary(events=[summary()['events'][0]] * 13),
            summary(tones=[{'hz': 1200.0, 'above_db': 8.1}]),
            summary(level_max_1s=[0.0] * 901),
            summary(strongest_background_hz='53'),
        ]
        for value in bad:
            with self.assertRaises(ProtocolError):
                validate_analysis(value)

    def test_evidence_states_levels_relative_to_the_background(self):
        evidence = explain_evidence(validate_analysis(summary()), 'The grinder started near the end.')
        self.assertEqual(evidence['voice_note'], 'The grinder started near the end.')
        self.assertAlmostEqual(evidence['analysis']['max_over_background_db'], 28.4)
        self.assertAlmostEqual(evidence['analysis']['loud_over_background_db'], 4.6)
        self.assertNotIn('level_max_1s', evidence['analysis'])
        self.assertEqual(evidence['level_trend']['loudest_second_over_background_db'], [1.7, 5.3, 28.4, 3.2])


class SoundExplainServiceTests(unittest.IsolatedAsyncioTestCase):
    send = spoken.SessionCase.send
    ask = spoken.SessionCase.ask
    asyncTearDown = spoken.SessionCase.asyncTearDown

    async def open(self, transcriber):
        self.sent = []
        async def send(message): self.sent.append(message)
        self.speaker = FakeSpeaker(seconds=0.2)
        self.service = Session(self.root / 'run', send, provider=self.provider,
                                   transcriber=transcriber, speaker=self.speaker)
        await self.send('hello')

    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.transcriber = spoken.FakeTranscriber('The grinder started near the end.')
        self.provider = RecordingExplainer()
        await self.open(self.transcriber)

    async def explain(self, key='explain-1', value=None):
        await self.send('analysis_explain', request_id=key, analysis=value or summary())
        await self.service.drain()
        return self.sent[-1]

    async def test_voice_note_steers_the_explanation(self):
        transcript = await self.ask()
        self.assertEqual(transcript['text'], 'The grinder started near the end.')
        await self.send('question_confirm', question_id='session-q1', accepted=True)
        reply = await self.explain()
        self.assertEqual(reply['type'], 'analysis_reply')
        self.assertEqual(reply['request_id'], 'explain-1')
        self.assertIn('The grinder started near the end.', reply['text'])
        self.assertEqual(self.provider.evidence[0]['voice_note'], 'The grinder started near the end.')

    async def test_explains_without_a_note(self):
        reply = await self.explain()
        self.assertEqual(reply['type'], 'analysis_reply')
        self.assertIsNone(self.provider.evidence[0]['voice_note'])

    async def test_explanation_is_spoken_once(self):
        reply = await self.explain()
        await self.send('speak', request_id='explain-1')
        await self.service.drain_speech()
        self.assertEqual(self.speaker.texts, [reply['text']])
        self.assertEqual(self.sent[-1]['type'], 'speech_end')
        with self.assertRaises(ProtocolError):
            await self.send('speak', request_id='explain-1')

    async def test_only_once(self):
        await self.explain()
        with self.assertRaises(ProtocolError):
            await self.explain('explain-2')

    async def test_invalid_summary_is_rejected(self):
        with self.assertRaises(ProtocolError):
            await self.send('analysis_explain', request_id='explain-1', analysis=summary(extra=1))

    async def test_prose_with_unbacked_numbers_is_refused(self):
        def invented(evidence):
            return 'It peaked 97 dB above the background.'
        self.provider.explain = invented
        reply = await self.explain()
        self.assertEqual(reply['type'], 'incomplete')


if __name__ == '__main__':
    unittest.main()
