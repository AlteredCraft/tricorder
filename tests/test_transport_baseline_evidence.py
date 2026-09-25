"""G-0001.02 C1: upload and spoken-guidance playback baselines from SD replay events."""
import copy
import unittest

from tools.transport_baseline_evidence import assess


def upload(n, ok=True, upload_us=4_000_000, max_chunk_us=90_000):
    return dict(event='investigation_upload', boot_id='boot', capture_id=f'c{n}', ok=ok, bytes=1152000,
                chunks=282 if ok else 100, upload_us=upload_us, max_chunk_us=max_chunk_us)


def speech(n, frames=8 * 24000, **changes):
    row = dict(event='investigation_speech', boot_id='boot', request_id=f'r{n}', status='complete',
               frames=frames, played_frames=frames, speaker_open=True, stopped=False, action=0,
               underruns=0, first_audio_ms=700)
    row.update(changes)
    return row


def end(state='complete'):
    return dict(event='investigation_end', boot_id='boot', session_id='ab-x', state=state, replay=True)


def run(replays=8):
    events = [dict(event='boot', boot_id='boot')]
    for i in range(replays):
        events += [upload(2 * i), speech(2 * i), upload(2 * i + 1), speech(2 * i + 1), end()]
    return events


class TransportBaselineTests(unittest.TestCase):
    def test_sixty_seconds_of_each_stream_without_loss_passes(self):
        result = assess(run())
        self.assertEqual(result['status'], 'pass', result['errors'])
        up, out = result['upload'], result['playback']
        self.assertEqual((up['captures'], up['consumed'], up['dropped']), (16, 16, 0))
        self.assertEqual(up['chunks_sent'], 16 * 282)
        self.assertAlmostEqual(up['active_s'], 64.0)
        self.assertAlmostEqual(up['throughput_kib_s'], 1152000 / 4 / 1024, places=3)
        self.assertEqual(up['max_chunk_ms'], 90.0)
        self.assertEqual((out['requests'], out['frames_received'], out['frames_played'], out['underruns']),
                         (16, 16 * 8 * 24000, 16 * 8 * 24000, 0))
        self.assertAlmostEqual(out['played_s'], 128.0)
        self.assertEqual(result['replays'], dict(ended=8, complete=8))

    def test_under_sixty_seconds_is_inconclusive_not_pass(self):
        result = assess(run(replays=3))
        self.assertEqual(result['status'], 'inconclusive')
        self.assertEqual(result['errors'], [])

    def test_loss_underrun_stop_reset_or_incomplete_replay_fails(self):
        cases = {
            'failed upload': lambda e: e.insert(1, upload(99, ok=False)),
            'chunk count': lambda e: e[1].update(chunks=281),
            'underrun': lambda e: e[2].update(underruns=1),
            'short playback': lambda e: e[2].update(played_frames=e[2]['frames'] - 480),
            'stopped': lambda e: e[2].update(stopped=True, status='stopped'),
            'speaker closed': lambda e: e[2].update(speaker_open=False),
            'second boot': lambda e: e.append(dict(event='boot', boot_id='other')),
            'incomplete replay': lambda e: e.append(end('failed')),
        }
        for name, mutate in cases.items():
            with self.subTest(name):
                events = copy.deepcopy(run())
                mutate(events)
                result = assess(events)
                self.assertEqual(result['status'], 'fail')
                self.assertTrue(result['errors'])

    def test_host_frame_counts_must_match_what_the_device_received(self):
        events = run()
        host = [dict(type='speech_output', status='complete', frames=8 * 24000) for _ in range(16)]
        result = assess(events, host)
        self.assertEqual(result['status'], 'pass', result['errors'])
        self.assertEqual(result['playback']['frames_produced'], 16 * 8 * 24000)
        host[3]['frames'] -= 1
        self.assertEqual(assess(events, host)['status'], 'fail')
        self.assertEqual(assess(events, host[:-1])['status'], 'fail')

    def test_no_events_is_inconclusive(self):
        self.assertEqual(assess([dict(event='boot', boot_id='boot')])['status'], 'inconclusive')


if __name__ == '__main__':
    unittest.main()
