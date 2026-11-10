"""F-0002 T5: the agent explains an on-device sound analysis, steered by a voice note."""
import asyncio
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from tools.investigation import MockProvider, ProtocolError
from tools.investigation_service import MockSession
from tools.sound_explain import explain_evidence, validate_analysis
from test_investigation import fixture
import test_spoken_ask_service as spoken
from test_spoken_guidance import FakeSpeaker
from tools.text_to_speech import spoken_form


def summary(**changes):
    value = {
        'duration_s': 41.4, 'background_db': -48.4, 'loud_db': -43.8, 'average_db': -45.6,
        'max_db': -20.0, 'max_at_s': 8.5, 'threshold_db': -38.4, 'strongest_background_hz': 53.2,
        'event_count': 1,
        'events': [{'start_s': 15.3, 'duration_s': 0.34, 'peak_over_db': 11.3, 'band_hz': 6110.0,
                    'band_rise_db': 14.7}],
        'tones': [{'tone_hz': 1200.0, 'above_db': 8.1}],
        'sharp_count': 2,
        'sharp': [{'at_s': 8.5, 'peak_over_db': 28.4}, {'at_s': 30.1, 'peak_over_db': 12.0}],
        'level_max_1s': [-46.7, -43.1, -20.0, -45.2],
    }
    value.update(changes)
    return value


class RecordingExplainer(MockProvider):
    def __init__(self):
        self.evidence = []

    def explain(self, evidence):
        self.evidence.append(deepcopy(evidence))
        return super().explain(evidence)


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
    send = spoken.SpokenAskServiceTests.send
    ask = spoken.SpokenAskServiceTests.ask
    asyncTearDown = spoken.SpokenAskServiceTests.asyncTearDown

    async def open(self, transcriber):
        self.sent = []
        async def send(message): self.sent.append(message)
        self.speaker = FakeSpeaker(seconds=0.2)
        self.service = MockSession(self.root / 'run', send, provider=self.provider,
                                   transcriber=transcriber, speaker=self.speaker)
        await self.send('hello', fixture=fixture().to_dict())

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
        self.assertEqual(self.speaker.texts, [spoken_form(reply['text'])])
        self.assertEqual(self.sent[-1]['type'], 'speech_end')
        with self.assertRaises(ProtocolError):
            await self.send('speak', request_id='explain-1')

    async def test_only_once_and_not_after_a_capture_or_mid_question(self):
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
