"""End-of-turn to first sound, by stage (tools/turn_timing_evidence.py; G-0001.04 C4)."""
import unittest

from tools.turn_timing_evidence import assess

MS = 1000


def turn(t, upload_ms=4000, reply_ms=1500, first_audio_ms=150):
    """One turn on the device clock: upload, turn -> reply (ack sent), speak, first audio."""
    up = t
    end = up + upload_ms * MS
    ack = end + 5 * MS + reply_ms * MS
    speak = ack + 20 * MS
    return [dict(event='investigation_state', state='uploading', device_us=up),
            dict(event='investigation_transport', message_type='capture_end', device_us=end),
            dict(event='investigation_transport', message_type='turn', device_us=end + 5 * MS),
            dict(event='investigation_transport', message_type='ack', device_us=ack),
            dict(event='investigation_transport', message_type='speak', device_us=speak),
            dict(event='investigation_speech', request_id='r1', first_audio_ms=first_audio_ms, status='complete',
                 device_us=speak + 20_000 * MS)], speak + 30_000 * MS


def run(n=30, **changes):
    events, t = [], 0
    for _ in range(n):
        rows, t = turn(t, **changes)
        events += rows
    return events


class TurnTimingTests(unittest.TestCase):
    def test_stages_and_p95(self):
        r = assess(run())
        # The target runs from the end of the turn, so a 4 s upload alone misses it.
        self.assertEqual(r['status'], 'fail')
        self.assertIn('end-of-turn', r['errors'][0])
        self.assertEqual(r['turns'], 30)
        self.assertEqual(r['end_of_turn_to_sound_ms']['p95'], 5675.0)   # 4000 upload + 5 + 1500 + 20 + 150
        self.assertEqual(r['after_upload_to_sound_ms']['p95'], 1675.0)   # reported, not the target
        self.assertEqual(r['stages_ms']['reply']['p95'], 1500.0)
        self.assertEqual(r['stages_ms']['first_audio']['p95'], 150.0)

    def test_fast_upload_passes(self):
        r = assess(run(upload_ms=500))
        self.assertEqual(r['status'], 'pass', r['errors'])
        self.assertEqual(r['end_of_turn_to_sound_ms']['p95'], 2175.0)

    def test_slow_reply_fails_and_few_turns_are_inconclusive(self):
        self.assertEqual(assess(run(upload_ms=500, reply_ms=2600))['status'], 'fail')
        self.assertEqual(assess(run(n=10, upload_ms=500))['status'], 'inconclusive')


if __name__ == '__main__':
    unittest.main()
