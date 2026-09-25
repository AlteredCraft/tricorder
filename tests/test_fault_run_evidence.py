"""Cancel, stall and outage runs (tools/fault_run_evidence.py; G-0001.02 C3, G-0001.04 C2/C3)."""
import unittest

from tools.fault_run_evidence import assess

MS = 1000


def ev(event, t, **fields):
    return dict(event=event, device_us=t, boot_id='b', host_receipt_ns=t * 1000 + 5_000_000_000, **fields)


def end(t, state, ui_max_ms=90):
    return ev('investigation_end', t, state=state, session_id='s', ui_p95_ms=38, ui_max_us=ui_max_ms * MS,
              ui_over_200_ms=0, free_internal=150_000, free_psram=16_000_000)


def cancel_session(t0, stop_after_ms=12):
    t = t0
    rows = [ev('replay_requested', t, accepted=True),
            ev('investigation_state', t + 100 * MS, state='uploading', session_id='s'),
            ev('investigation_transport', t + 200 * MS, message_type='capture_start'),
            ev('investigation_state', t + 5000 * MS, state='adjust', session_id='s'),
            ev('investigation_transport', t + 5010 * MS, message_type='speak'),
            ev('console_tap', t + 7000 * MS + 900, button='cancel', accepted=True, tap_us=t + 7000 * MS),
            ev('investigation_speech', t + 7050 * MS, stopped=True, stopped_us=t + 7000 * MS + stop_after_ms * MS,
               status='stopped', request_id='r1'),
            ev('investigation_cancel', t + 7060 * MS, requested_device_us=t + 7000 * MS,
               owner_stopped_device_us=t + 7055 * MS, session_id='s'),
            ev('investigation_transport', t + 7061 * MS, message_type='cancel'),
            end(t + 7100 * MS, 'cancelled')]
    return rows, t + 9000 * MS


class FaultRunTests(unittest.TestCase):
    def cancels(self, n=20, **changes):
        events, t = [ev('boot', 0)], 1_000_000
        for _ in range(n):
            rows, t = cancel_session(t, **changes)
            events += rows
        return events

    def test_cancel_trials(self):
        r = assess(self.cancels())
        self.assertEqual(r['status'], 'pass', r['errors'])
        c = r['cancel']
        self.assertEqual((c['trials'], c['stop_ms']['p95'], c['owner_stop_ms']['p95']), (20, 12.0, 55.0))
        self.assertEqual(c['old_session_actions'], 0)
        self.assertEqual(r['sessions']['end_states'], {'cancelled': 20})

    def test_slow_stop_and_old_session_action_fail(self):
        self.assertEqual(assess(self.cancels(stop_after_ms=151))['status'], 'fail')
        events = self.cancels()
        i = next(i for i, e in enumerate(events) if e['event'] == 'investigation_cancel')
        events.insert(i + 1, ev('investigation_transport', events[i]['device_us'] + 1, message_type='turn'))
        r = assess(events)
        self.assertEqual((r['status'], r['cancel']['old_session_actions']), ('fail', 1))

    def test_stall_ends_visibly_without_reset_and_keeps_the_ui_on_target(self):
        events = [ev('boot', 0), ev('investigation_state', 1000, state='uploading', session_id='s'),
                  ev('storage_archive', 2000, result='pass', capture_id='s-a'),
                  end(3000, 'offline'), ev('investigation_state', 4000, state='ready_a', session_id='t'),
                  end(5000, 'complete')]
        host = [dict(action='service_pause', host_ns=1), dict(action='service_resume', host_ns=4_000_000_000)]
        r = assess(events, host)
        self.assertEqual(r['status'], 'pass', r['errors'])
        self.assertEqual(r['sessions']['end_states'], {'offline': 1, 'complete': 1})
        self.assertEqual(r['storage'], dict(archived=1, failed=0))
        for bad in (dict(ui_max_ms=201), None):
            with self.subTest(bad=bad):
                changed = [dict(e) for e in events]
                if bad:
                    changed[3] = end(3000, 'offline', **bad)
                else:
                    changed.append(ev('boot', 9000))
                self.assertEqual(assess(changed, host)['status'], 'fail')
        hung = [e for e in events if e['event'] != 'investigation_end' or e['state'] != 'offline']
        self.assertEqual(assess(hung[:3], host)['status'], 'fail')  # the stalled session never ended

    def test_a_session_that_rides_out_the_pause_counts_as_recovered(self):
        events = [ev('boot', 0), ev('investigation_state', 1000, state='ready_a', session_id='s'),
                  dict(end(2000, 'complete'), host_receipt_ns=20_000_000_000),
                  dict(ev('investigation_state', 3000, state='ready_a', session_id='t'), host_receipt_ns=45_000_000_000),
                  dict(end(4000, 'complete'), host_receipt_ns=60_000_000_000)]
        host = [dict(action='service_pause', host_ns=5_000_000_000), dict(action='service_resume', host_ns=15_000_000_000)]
        r = assess(events, host)
        self.assertEqual((r['status'], r['recovery_s'], r['survived_pauses']), ('pass', [], 1), r['errors'])

    def test_a_run_where_no_session_connects_fails(self):
        events = [ev('boot', 0), ev('investigation_state', 1000, state='offline', session_id='s'), end(2000, 'offline')]
        r = assess(events)
        self.assertEqual(r['status'], 'fail')
        self.assertIn('no session connected to the service', r['errors'])

    def test_recovery_after_resume_uses_host_clocks_only(self):
        # Resume at host 10.0 s; the next session reaches ready_a at host 12.5 s.
        events = [ev('boot', 0), end(1000, 'incomplete'),
                  dict(ev('investigation_state', 2000, state='ready_a', session_id='t'), host_receipt_ns=12_500_000_000),
                  end(3000, 'complete')]
        host = [dict(action='service_pause', host_ns=1_000_000_000), dict(action='service_resume', host_ns=10_000_000_000)]
        r = assess(events, host)
        self.assertEqual(r['recovery_s'], [2.5])
        self.assertEqual(r['status'], 'pass', r['errors'])
        events[2]['host_receipt_ns'] = 15_500_000_000
        self.assertEqual(assess(events, host)['status'], 'fail')


if __name__ == '__main__':
    unittest.main()
