"""Assess a driven run with cancels or service pauses (capture_serial --drive-sessions).

- Every session ends (complete, cancelled, offline or incomplete are all
  visible outcomes); one boot, no reset.
- The LVGL probe stays on target in every session: p95 <= 50 ms, max <= 200 ms.
- SD archives pass (captures retained intact).
- Cancel (G-0001.04 C3): the tap to the playback stop, p95 <= 150 ms, on the
  device clock; after the tap the session sends nothing but cancel/speech_stop.
- Recovery: after each service resume, either the paused session completes,
  or a new session reaches ready_a within 5 s. Both times are on the Mac clock (resume time and the event's
  host_receipt_ns); device and Mac clocks are never subtracted.
"""
import argparse
from collections import Counter
import json
from pathlib import Path

from tools.session_run_evidence import stats

ALLOWED_AFTER_CANCEL = ('cancel', 'speech_stop')
NOT_CONNECTED = ('idle', 'connecting', 'offline', 'incomplete')


def assess(events, host_actions=None, *, stop_p95_ms=150, recovery_limit_s=5, ui_p95_ms=50, ui_max_ms=200):
    errors = []
    boots = [e for e in events if e.get('event') == 'boot']
    if len(boots) != 1:
        errors.append(f'{len(boots)} boots: a reset or crash during the run')
    ends = [e for e in events if e.get('event') == 'investigation_end']
    last_end = max((i for i, e in enumerate(events) if e.get('event') == 'investigation_end'), default=-1)
    if any(e.get('event') == 'investigation_state' for e in events[last_end + 1:]):
        errors.append('a session never ended')
    if ends and not any(e.get('event') == 'investigation_state' and e.get('state') not in NOT_CONNECTED
                        for e in events):
        errors.append('no session connected to the service')
    for e in ends:
        if e['ui_p95_ms'] > ui_p95_ms or e['ui_max_us'] > ui_max_ms * 1000:
            errors.append(f"UI off target in a {e['state']} session: p95 {e['ui_p95_ms']} ms, "
                          f"max {e['ui_max_us'] / 1000} ms")

    archives = [e for e in events if e.get('event') == 'storage_archive']
    storage = dict(archived=sum(a['result'] == 'pass' for a in archives),
                   failed=sum(a['result'] != 'pass' for a in archives))
    if storage['failed']:
        errors.append(f"{storage['failed']} SD archives failed")

    stops, owner_stops, old_actions, cancelling, last_speech = [], [], 0, False, None
    for e in events:
        kind = e.get('event')
        if kind == 'console_tap' and e.get('button') == 'cancel' and e.get('accepted'):
            cancelling = True
        elif kind == 'investigation_speech':
            last_speech = e
        elif kind == 'investigation_cancel':
            requested = e['requested_device_us']
            owner_stops.append((e['owner_stopped_device_us'] - requested) / 1000)
            if last_speech and last_speech.get('stopped_us', 0) >= requested:
                stops.append((last_speech['stopped_us'] - requested) / 1000)
        elif kind == 'investigation_transport' and cancelling and e.get('message_type') not in ALLOWED_AFTER_CANCEL:
            old_actions += 1
        elif kind == 'investigation_end':
            cancelling, last_speech = False, None
    cancel = dict(trials=len(owner_stops), stop_ms=stats(stops), owner_stop_ms=stats(owner_stops),
                  old_session_actions=old_actions)
    if stops and cancel['stop_ms']['p95'] > stop_p95_ms:
        errors.append(f"cancel-to-playback-stop p95 {cancel['stop_ms']['p95']} ms > {stop_p95_ms} ms")
    if old_actions:
        errors.append(f'{old_actions} messages from a cancelled session after its cancel')

    recovery, survived_pauses = [], 0
    for action in host_actions or []:
        if action['action'] != 'service_resume':
            continue
        ready = next((e for e in events if e.get('event') == 'investigation_state' and e.get('state') == 'ready_a'
                      and e['host_receipt_ns'] >= action['host_ns']), None)
        # A session that rides out the pause and completes needs no fresh session.
        survived = next((e for e in events if e.get('event') == 'investigation_end'
                         and e['host_receipt_ns'] >= action['host_ns']), None)
        if survived is not None and survived['state'] == 'complete' and (
                ready is None or survived['host_receipt_ns'] <= ready['host_receipt_ns']):
            survived_pauses += 1
            continue
        if ready is None:
            errors.append('no new session reached ready_a after a service resume')
            continue
        recovery.append(round((ready['host_receipt_ns'] - action['host_ns']) / 1e9, 3))
    if any(s > recovery_limit_s for s in recovery):
        errors.append(f'fresh session later than {recovery_limit_s} s after resume: {recovery}')

    return dict(status='fail' if errors else 'pass', errors=errors,
                sessions=dict(ended=len(ends), end_states=dict(Counter(e['state'] for e in ends))),
                ui=dict(worst_p95_ms=max((e['ui_p95_ms'] for e in ends), default=None),
                        max_ms=max((e['ui_max_us'] for e in ends), default=0) / 1000),
                storage=storage, cancel=cancel, recovery_s=recovery, survived_pauses=survived_pauses,
                scope='Console taps through the LVGL click handlers; service stalls/outages by SIGSTOP/SIGCONT '
                      'of the Mac service process.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path, help='capture_serial output directory')
    args = parser.parse_args()
    events = [json.loads(line) for line in (args.run / 'events.jsonl').read_text().splitlines()]
    summary = json.loads((args.run / 'summary.json').read_text())
    result = assess(events, summary.get('host_actions'))
    if any(summary.get(key) for key in ('integrity_errors', 'capture_errors', 'incomplete_captures')):
        result['errors'].append('run/capture integrity failed')
        result['status'] = 'fail'
    with (args.run / 'fault-run.json').open('x') as output:
        json.dump(result, output, indent=2)
        output.write('\n')
    print(json.dumps(result, indent=2))
    if result['status'] != 'pass':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
