"""F-0007: the agent explains an on-device power analysis."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from tools.investigation import ProtocolError
from tools.investigation_service import MockSession
from tools.power_explain import checked_text, explain_evidence, validate_analysis
from test_investigation import fixture
from test_sound_explain import RecordingExplainer
import test_spoken_ask_service as spoken
from test_spoken_guidance import FakeSpeaker


def summary(**changes):
    value = {
        'kind': 'power', 'duration_s': 70.0, 'source': 'battery', 'battery_s': 60, 'charging_s': 10, 'no_current_s': 0,
        'volts_start_v': 8.2, 'volts_end_v': 8.3, 'volts_min_v': 8.2, 'volts_max_v': 8.3,
        'draw_typical_ma': 500.0, 'draw_min_ma': 497.0, 'draw_max_ma': 653.0, 'draw_max_at_s': 20.5,
        'charge_typical_ma': 400.0, 'power_typical_mw': 4100.0, 'power_max_mw': 5355.0,
        'used_mah': 9.2, 'used_mwh': 75.0, 'charged_mah': 1.1, 'battery_pct': 94.0,
        'step_count': 3,
        'steps': [{'at_s': 20.0, 'from_ma': 500.0, 'to_ma': 650.0}, {'at_s': 40.0, 'from_ma': 650.0, 'to_ma': 500.0},
                  {'at_s': 60.0, 'from_ma': 500.0, 'to_ma': -400.0}],
        'screen_changes': [{'at_s': 20.0, 'brightness_pct': 100, 'before_ma': 500.0, 'after_ma': 650.0},
                           {'at_s': 40.0, 'brightness_pct': 50, 'before_ma': 650.0, 'after_ma': 500.0}],
        'current_1s_ma': [500.0, 501.0, 650.0, -400.0], 'volts_1s_v': [8.2, 8.2, 8.19, 8.3],
    }
    value.update(changes)
    return value


class ValidatePowerAnalysisTests(unittest.TestCase):
    def test_accepts_a_device_summary(self):
        checked = validate_analysis(summary())
        self.assertEqual(checked['step_count'], 3)
        self.assertEqual(checked['screen_changes'][0]['brightness_pct'], 100.0)
        self.assertIsNone(validate_analysis(summary(battery_pct=None))['battery_pct'])

    def test_rejects_malformed_summaries(self):
        bad = [
            summary(extra=1),
            summary(kind='motion'),
            summary(draw_typical_ma=float('nan')),
            summary(duration_s=0),
            summary(battery_s=-1),
            summary(step_count=True),
            summary(source='usb'),
            summary(battery_pct=101.0),
            summary(steps=[summary()['steps'][0]] * 13),
            summary(step_count=4),
            summary(screen_changes=[{'at_s': 20.0, 'brightness': 100, 'before_ma': 500.0, 'after_ma': 650.0}]),
            summary(volts_1s_v=[8.2]),
            summary(current_1s_ma=[0.0] * 601, volts_1s_v=[8.0] * 601),
            summary(volts_max_v=21.0),
        ]
        for value in bad:
            with self.assertRaises(ProtocolError):
                validate_analysis(value)

    def test_evidence_and_number_check(self):
        evidence = explain_evidence(validate_analysis(summary()))
        self.assertEqual(evidence['kind'], 'power')
        self.assertNotIn('current_1s_ma', evidence['analysis'])
        self.assertEqual(evidence['trend']['each_second_volts_v'], [8.2, 8.2, 8.19, 8.3])
        fine = ('On battery for a minute at about 500 mA, 4.1 W, or 4100 mW; the screen at 100% took it to 650 mA at 0:20. '
                'The pack sat near 8.2 V, roughly 94 percent, and 9 mAh (75 mWh) were used before charging at 400 mA.')
        self.assertEqual(checked_text(fine, evidence), fine)
        for invented in ('It drew 1.2 A.', 'About 3 W.', 'It fell to 7.5 V.', 'Some 20 mAh were used.',
                         'Roughly 30 percent full.', 'A 60 Hz hum.'):
            with self.assertRaises(ProtocolError):
                checked_text(invented, evidence)


class PowerExplainServiceTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_explains_a_power_analysis(self):
        reply = await self.explain(summary())
        self.assertEqual(reply['type'], 'analysis_reply')
        self.assertIn('500 mA', reply['text'])
        self.assertEqual(self.provider.evidence[0]['kind'], 'power')

    async def test_prose_with_unbacked_numbers_is_refused(self):
        self.provider.explain = lambda evidence: 'It drew 1.5 A.'
        reply = await self.explain(summary())
        self.assertEqual(reply['type'], 'incomplete')


if __name__ == '__main__':
    unittest.main()
