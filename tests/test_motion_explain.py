"""F-0005: the agent explains an on-device motion analysis."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from tools.investigation import ProtocolError
from tools.investigation_service import MockSession
from tools.motion_explain import checked_text, explain_evidence, validate_analysis
from test_investigation import fixture
from test_sound_explain import RecordingExplainer, summary as sound_summary
import test_spoken_ask_service as spoken
from test_spoken_guidance import FakeSpeaker


def summary(**changes):
    value = {
        'kind': 'motion', 'duration_s': 25.0, 'gravity_g': 0.996, 'quiet_g': 0.002, 'threshold_g': 0.102,
        'peak_g': 0.812, 'peak_at_s': 20.6, 'typical_g': 0.015, 'steadiest_g': 0.003, 'steadiest_at_s': 2.0,
        'shakiest_g': 0.571, 'shakiest_at_s': 22.0, 'tilt_min_deg': 0.3, 'tilt_max_deg': 89.8, 'rest_s': 8.0,
        'steadiness': 'in hand', 'still_s': 9, 'in_hand_s': 10, 'moving_s': 6,
        'orientation': 'flat', 'flat_s': 15, 'tilted_s': 0, 'upright_s': 10,
        'event_count': 2,
        'events': [{'start_s': 5.0, 'duration_s': 0.03, 'peak_g': 0.5},
                   {'start_s': 20.01, 'duration_s': 4.98, 'peak_g': 0.812}],
        'vibration': {'vibration_hz': 25.0, 'vibration_mg': 4.0},
        'movement_1s_mg': [3.1, 2.9, 15.2], 'tilt_1s_deg': [0.3, 0.4, 89.8],
    }
    value.update(changes)
    return value


class ValidateMotionAnalysisTests(unittest.TestCase):
    def test_accepts_a_device_summary(self):
        checked = validate_analysis(summary())
        self.assertEqual(checked['event_count'], 2)
        self.assertEqual(checked['vibration']['vibration_hz'], 25.0)
        self.assertIsNone(validate_analysis(summary(vibration=None))['vibration'])

    def test_rejects_malformed_summaries(self):
        bad = [
            summary(extra=1),
            summary(kind='sound'),
            summary(peak_g=float('nan')),
            summary(duration_s=0),
            summary(event_count=-1),
            summary(still_s=True),
            summary(steadiness='calm'),
            summary(orientation='sideways'),
            summary(events=[summary()['events'][0]] * 13),
            summary(event_count=3),
            summary(vibration={'hz': 25.0, 'vibration_mg': 4.0}),
            summary(tilt_1s_deg=[0.3]),
            summary(movement_1s_mg=[0.0] * 601, tilt_1s_deg=[0.0] * 601),
            summary(tilt_max_deg=91.0),
        ]
        for value in bad:
            with self.assertRaises(ProtocolError):
                validate_analysis(value)

    def test_evidence_and_number_check(self):
        evidence = explain_evidence(validate_analysis(summary()))
        self.assertEqual(evidence['kind'], 'motion')
        self.assertNotIn('movement_1s_mg', evidence['analysis'])
        self.assertEqual(evidence['trend']['each_second_tilt_deg'], [0.3, 0.4, 89.8])
        fine = ('You held it, then shook it at 0:20; the biggest jolt was 0.81 g, or 812 mg. '
                'It lay flat, tilting up to 90 degrees, and rested with a 25 Hz vibration of 4 mg.')
        self.assertEqual(checked_text(fine, evidence), fine)
        for invented in ('It hit 2.5 g.', 'It tilted 45 degrees.', 'A 60 Hz hum.', 'About 30 mg of tremor.'):
            with self.assertRaises(ProtocolError):
                checked_text(invented, evidence)


class MotionExplainServiceTests(unittest.IsolatedAsyncioTestCase):
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

    async def explain(self, value):
        await self.send('analysis_explain', request_id='explain-1', analysis=deepcopy(value))
        await self.service.drain()
        return self.sent[-1]

    async def test_explains_a_motion_analysis(self):
        reply = await self.explain(summary())
        self.assertEqual(reply['type'], 'analysis_reply')
        self.assertIn('in hand', reply['text'])
        self.assertEqual(self.provider.evidence[0]['kind'], 'motion')

    async def test_sound_with_its_kind_still_explains(self):
        reply = await self.explain(sound_summary(kind='sound'))
        self.assertEqual(reply['type'], 'analysis_reply')
        self.assertNotIn('kind', self.provider.evidence[0])

    async def test_unknown_kind_is_rejected(self):
        with self.assertRaises(ProtocolError):
            await self.send('analysis_explain', request_id='explain-1', analysis=summary(kind='light'))

    async def test_prose_with_unbacked_numbers_is_refused(self):
        self.provider.explain = lambda evidence: 'It peaked at 3.2 g.'
        reply = await self.explain(summary())
        self.assertEqual(reply['type'], 'incomplete')


if __name__ == '__main__':
    unittest.main()
