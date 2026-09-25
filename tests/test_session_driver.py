"""Automated guided sessions over the USB console (tools/session_driver.py)."""
import unittest

from tools.session_driver import SessionDriver


class Clock:
    def __init__(self): self.now = 100.0
    def __call__(self): return self.now


def state(name): return dict(event='investigation_state', state=name, session_id='s')
def end(name='complete'): return dict(event='investigation_end', state=name, session_id='s')
def tap(button, accepted): return dict(event='console_tap', button=button, accepted=accepted)
READY = dict(event='check', check='storage_http', result='pass')


class SessionDriverTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()

    def run_until(self, driver, seconds):
        out = []
        for _ in range(int(seconds * 10) + 1):  # 0.1 s steps, one past the span
            self.clock.now = round(self.clock.now + 0.1, 6)
            out += driver.due()
        return out

    def test_taps_each_waiting_step_then_starts_the_next_session(self):
        d = SessionDriver(2, delay_s=1.0, clock=self.clock)
        self.assertEqual(self.run_until(d, 5), [])          # nothing before the device is ready
        d.on_event(READY)
        self.assertEqual(self.run_until(d, 1.05), [('tap', 'start')])
        for step in ('connecting', 'ready_a', 'recording_a', 'uploading', 'waiting', 'adjust', 'ready_b',
                     'recording_b', 'uploading', 'return_a', 'recording_repeat', 'uploading', 'waiting', 'complete'):
            d.on_event(state(step))
            expected = [('tap', 'action')] if step in ('ready_a', 'adjust', 'ready_b', 'return_a') else []
            self.assertEqual(self.run_until(d, 1.05), expected, step)
        d.on_event(end())
        self.assertEqual(self.run_until(d, 1.05), [('tap', 'start')])
        self.assertFalse(d.done)
        d.on_event(end())
        self.assertTrue(d.done)
        self.assertEqual(self.run_until(d, 5), [])
        self.assertEqual(d.summary(), dict(sessions=2, started=2, ended=2, end_states={'complete': 2},
                                           rejected_taps=0))

    def test_rejected_taps_retry_while_the_step_still_waits(self):
        d = SessionDriver(1, delay_s=1.0, clock=self.clock)
        d.on_event(READY)
        self.run_until(d, 1.05)
        d.on_event(tap('start', False))                     # e.g. the endpoint was not loaded yet
        self.assertEqual(self.run_until(d, 1.05), [('tap', 'start')])
        d.on_event(state('return_a'))                       # first shown without its button (saving B)
        self.assertEqual(self.run_until(d, 1.05), [('tap', 'action')])
        d.on_event(tap('action', False))
        self.assertEqual(self.run_until(d, 0.55), [('tap', 'action')])
        d.on_event(state('recording_repeat'))
        d.on_event(tap('action', False))                    # a late rejection after the step moved on
        self.assertEqual(self.run_until(d, 2), [])
        self.assertEqual(d.summary()['rejected_taps'], 3)
        self.assertEqual(d.summary()['started'], 1)

    def test_cancel_at_a_state_replaces_the_action(self):
        d = SessionDriver(1, delay_s=1.0, cancel_at='adjust', cancel_delay_s=2.0, clock=self.clock)
        d.on_event(READY)
        self.run_until(d, 1.05)
        d.on_event(state('adjust'))
        self.assertEqual(self.run_until(d, 1.5), [])
        self.assertEqual(self.run_until(d, 0.6), [('tap', 'cancel')])
        d.on_event(state('cancelled'))
        d.on_event(end('cancelled'))
        self.assertTrue(d.done)

    def test_replay_sessions_start_with_the_replay_command_and_take_no_action_taps(self):
        d = SessionDriver(2, replay='ab-' + 'a' * 32, delay_s=1.0, clock=self.clock)
        d.on_event(READY)
        self.assertEqual(self.run_until(d, 1.05), [('replay', 'ab-' + 'a' * 32)])
        d.on_event(state('adjust'))
        self.assertEqual(self.run_until(d, 2), [])
        d.on_event(dict(event='replay_requested', accepted=False))
        self.assertEqual(self.run_until(d, 1.05), [('replay', 'ab-' + 'a' * 32)])

    def test_service_pause_at_a_state_resumes_after_its_duration(self):
        d = SessionDriver(2, delay_s=1.0, pause_at='uploading', pause_s=10, pause_every=2, clock=self.clock)
        d.on_event(READY)
        self.run_until(d, 1.05)
        d.on_event(state('uploading'))
        self.assertEqual(self.run_until(d, 12), [])        # session 1: not a pause session
        d.on_event(end())
        self.run_until(d, 1.05)
        d.on_event(state('uploading'))
        self.assertEqual(self.run_until(d, 0.15), [('pause', None)])
        self.assertEqual(self.run_until(d, 9.6), [])
        self.assertEqual(self.run_until(d, 0.3), [('resume', None)])
        d.on_event(state('uploading'))                      # once per session
        self.assertEqual(self.run_until(d, 12), [])

    def test_bounds(self):
        with self.assertRaises(ValueError):
            SessionDriver(0)
        with self.assertRaises(ValueError):
            SessionDriver(1, cancel_at='nonsense')


if __name__ == '__main__':
    unittest.main()
