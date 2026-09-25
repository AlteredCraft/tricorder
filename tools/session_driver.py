"""Drive guided sessions over the USB console for automated G-0001 runs.

Reacts to device events: taps the action button when a step waits for it
(TRICORDER_TAP reaches the same LVGL click handler as a finger, and only on an
enabled button), optionally taps Cancel at a chosen state, optionally pauses
the Mac service at a chosen state, and starts the next session after each
investigation_end. SD replay sessions start with TRICORDER_REPLAY and need no
action taps. `due()` returns the actions whose time has come:
('tap', button), ('replay', session), ('pause', None) or ('resume', None).
"""
from collections import Counter
import time

ACTION_STATES = ('ready_a', 'adjust', 'ready_b', 'return_a')
STATES = ('connecting', 'ready_a', 'recording_a', 'uploading', 'waiting', 'acknowledging', 'adjust',
          'ready_b', 'recording_b', 'return_a', 'recording_repeat', 'complete')


class SessionDriver:
    def __init__(self, sessions, *, replay=None, delay_s=1.0, cancel_at=None, cancel_delay_s=1.0,
                 pause_at=None, pause_s=10.0, pause_every=1, clock=None):
        if not 1 <= sessions <= 500:
            raise ValueError('sessions is 1 to 500')
        for name in (cancel_at, pause_at):
            if name is not None and name not in STATES:
                raise ValueError(f'unknown state {name!r}')
        self.sessions, self.replay, self.delay_s = sessions, replay, delay_s
        self.cancel_at, self.cancel_delay_s = cancel_at, cancel_delay_s
        self.pause_at, self.pause_s, self.pause_every = pause_at, pause_s, pause_every
        self.clock = clock or time.monotonic
        self.ready = False
        self.state = None
        self.started = self.ended = self.rejected = 0
        self.end_states = Counter()
        self.cancel_sent = self.paused_this = False
        self.pending = None  # (due, kind, argument): one next input at a time
        self.resume_due = None

    def start_action(self):
        return ('replay', self.replay) if self.replay else ('tap', 'start')

    def schedule(self, delay, kind, argument=None):
        self.pending = (self.clock() + delay, kind, argument)

    def on_event(self, event):
        kind = event.get('event')
        if kind == 'check' and event.get('check') == 'storage_http' and not self.ready:
            self.ready = True
            self.schedule(self.delay_s, *self.start_action())
        elif kind == 'investigation_state':
            self.state = event.get('state')
            if self.pause_at == self.state and not self.paused_this and self.started % self.pause_every == 0:
                self.paused_this = True
                self.pending = None
                self.schedule(0, 'pause')
            elif self.cancel_at == self.state and not self.cancel_sent:
                self.cancel_sent = True
                self.schedule(self.cancel_delay_s, 'tap', 'cancel')
            elif self.state in ACTION_STATES and not self.replay and not self.cancel_sent:
                self.schedule(self.delay_s, 'tap', 'action')
        elif kind == 'console_tap' and event.get('accepted') is False:
            self.rejected += 1
            button = event.get('button')
            if button == 'start':
                self.started -= 1
                self.schedule(1.0, 'tap', 'start')
            elif button == 'action' and self.state in ACTION_STATES:
                self.schedule(0.5, 'tap', 'action')
        elif kind == 'replay_requested' and event.get('accepted') is False:
            self.rejected += 1
            self.started -= 1
            self.schedule(1.0, *self.start_action())
        elif kind == 'investigation_end':
            self.ended += 1
            self.end_states[event.get('state')] += 1
            self.state = None
            self.cancel_sent = self.paused_this = False
            self.pending = None
            if self.started < self.sessions:
                self.schedule(self.delay_s, *self.start_action())

    def due(self):
        now = self.clock()
        out = []
        if self.resume_due is not None and now >= self.resume_due:
            self.resume_due = None
            out.append(('resume', None))
        if self.pending and now >= self.pending[0]:
            _, kind, argument = self.pending
            self.pending = None
            if kind == 'pause':
                self.resume_due = now + self.pause_s
            if (kind, argument) == self.start_action():
                self.started += 1
            out.append((kind, argument))
        return out

    @property
    def done(self):
        return self.ended >= self.sessions and self.resume_due is None

    def summary(self):
        return dict(sessions=self.sessions, started=self.started, ended=self.ended,
                    end_states=dict(self.end_states), rejected_taps=self.rejected)
