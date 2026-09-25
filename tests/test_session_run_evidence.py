"""Driven-session runs: UI intervals, input-to-submit, round trips, memory (G-0001.02 C2/C4, .04 C2)."""
import copy
import unittest

from tools.session_run_evidence import assess

T = 1_000_000  # device microseconds


def session(n, t0, free_psram=20_000_000, ui_p95=21, ui_max_us=60_000, state='complete'):
    """One driven live session: four action taps, two request/reply turns."""
    rows = [dict(event='console_tap', button='start', accepted=True, tap_us=t0, device_us=t0 + 300)]
    t = t0 + T
    for action in ('record_a', 'confirm_b', 'record_b', 'record_repeat'):
        rows.append(dict(event='console_tap', button='action', accepted=True, tap_us=t, device_us=t + 400))
        rows.append(dict(event='investigation_steadiness', action=action, device_us=t + 30_000))
        t += 5 * T
        if action in ('record_a', 'record_repeat'):
            rows.append(dict(event='investigation_upload', capture_id=f'{n}-{action}', ok=True, device_us=t))
            rows.append(dict(event='investigation_transport', message_type='turn', device_us=t + 1000))
            rows.append(dict(event='investigation_transport', message_type='ack', device_us=t + 81_000))
            rows.append(dict(event='investigation_state', state='adjust' if action == 'record_a' else 'complete',
                             device_us=t + 95_000))
        elif action == 'record_b':
            rows.append(dict(event='investigation_upload', capture_id=f'{n}-b', ok=True, device_us=t))
    rows.append(dict(event='investigation_end', state=state, replay=False, device_us=t + T, ui_intervals=1500,
                     ui_p50_ms=20, ui_p95_ms=ui_p95, ui_max_us=ui_max_us, ui_over_50_ms=2, ui_over_200_ms=0,
                     free_internal=150_000, free_psram=free_psram, largest_psram_block=8_000_000,
                     min_free_internal=120_000))
    return rows, t + 2 * T


def run(sessions=20, **changes):
    events, t = [dict(event='boot', boot_id='b', device_us=0)], 10 * T
    for n in range(sessions):
        rows, t = session(n, t, **changes)
        events += rows
    for e in events:
        e.setdefault('boot_id', 'b')
    return events


class SessionRunTests(unittest.TestCase):
    def test_clean_run_passes_each_target(self):
        r = assess(run())
        self.assertEqual(r['status'], 'pass', r['errors'])
        self.assertEqual(r['sessions'], dict(ended=20, end_states={'complete': 20}))
        self.assertEqual(r['input_events'], 100)
        self.assertEqual((r['ui']['worst_p95_ms'], r['ui']['max_ms']), (21, 60.0))
        self.assertEqual(r['input_to_submit_ms']['count'], 80)
        self.assertEqual(r['input_to_submit_ms']['p95'], 30.0)
        self.assertEqual(r['round_trip_ms']['turn_to_reply']['p95'], 80.0)
        self.assertEqual(r['round_trip_ms']['ack_to_state']['p95'], 14.0)
        self.assertEqual(r['captures'], dict(uploaded=60, failed=0))
        self.assertEqual(r['memory']['psram_change_pct'], 0.0)

    def test_targets_fail(self):
        cases = {
            'ui p95': dict(ui_p95=51),
            'ui max': dict(ui_max_us=200_001),
            'memory': None,
            'incomplete session': dict(state='incomplete'),
            'slow submit': None,
            'reset': None,
        }
        for name, changes in cases.items():
            with self.subTest(name):
                events = run(**(changes or {}))
                if name == 'memory':
                    ends = [e for e in events if e['event'] == 'investigation_end']
                    for e in ends[5:]:
                        e['free_psram'] = 18_000_000   # 10% below the post-warmup baseline
                if name == 'slow submit':
                    for e in events:
                        if e['event'] == 'investigation_steadiness':
                            e['device_us'] += 200_000
                if name == 'reset':
                    events.append(dict(event='boot', boot_id='c', device_us=0))
                r = assess(events)
                self.assertEqual(r['status'], 'fail')
                self.assertTrue(r['errors'])

    def test_fewer_than_100_input_events_is_inconclusive(self):
        r = assess(run(sessions=10))
        self.assertEqual(r['status'], 'inconclusive')
        self.assertEqual(r['errors'], [])


if __name__ == '__main__':
    unittest.main()
