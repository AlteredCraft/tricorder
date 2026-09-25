"""Assess a driven-session run (capture_serial --drive-sessions).

G-0001.02 C2: every session completes on one boot, >= 100 input events,
LVGL probe interval p95 <= 50 ms and max <= 200 ms in every session, and
input-to-submit p95 <= 100 ms (console tap to the media owner receiving the
action). C4: after two warm-up sessions, free internal RAM and PSRAM at each
session end stay within 5% of the third session's. G-0001.04 C2: round trips
on the device clock, turn sent to ack sent (the reply arrived in between) and
ack sent to the next state (the Mac's acknowledgement arrived in between).
"""
import argparse
from collections import Counter
import json
import math
from pathlib import Path

WARMUP_SESSIONS = 2


def p95(values):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def stats(values):
    return dict(count=len(values), p95=p95(values), max=max(values) if values else None)


def assess(events, *, ui_p95_ms=50, ui_max_ms=200, submit_p95_ms=100, memory_pct=5, min_inputs=100,
           round_trip_p95_ms=200):
    errors = []
    boots = {e['boot_id'] for e in events if e.get('event') == 'boot'}
    if len(boots) != 1:
        errors.append(f'{len(boots)} boots: a reset or crash during the run')
    ends = [e for e in events if e.get('event') == 'investigation_end']
    end_states = Counter(e['state'] for e in ends)
    if set(end_states) - {'complete'}:
        errors.append(f'sessions not complete: {dict(end_states)}')

    taps = [e for e in events if e.get('event') == 'console_tap' and e.get('accepted')]
    submits, pending = [], None
    for e in events:
        if e.get('event') == 'console_tap' and e.get('accepted') and e.get('button') == 'action':
            pending = e['tap_us']
        elif e.get('event') == 'investigation_steadiness' and pending is not None:
            submits.append((e['device_us'] - pending) / 1000)
            pending = None

    turns, acks, last_turn, last_ack = [], [], None, None
    for e in events:
        if e.get('event') == 'investigation_transport' and e.get('message_type') == 'turn':
            last_turn = e['device_us']
        elif e.get('event') == 'investigation_transport' and e.get('message_type') == 'ack':
            if last_turn is not None:
                turns.append((e['device_us'] - last_turn) / 1000)
            last_turn, last_ack = None, e['device_us']
        elif e.get('event') == 'investigation_state' and last_ack is not None:
            acks.append((e['device_us'] - last_ack) / 1000)
            last_ack = None

    ui = dict(sessions=len(ends), worst_p95_ms=max((e['ui_p95_ms'] for e in ends), default=None),
              max_ms=max((e['ui_max_us'] for e in ends), default=0) / 1000,
              over_50=sum(e['ui_over_50_ms'] for e in ends), over_200=sum(e['ui_over_200_ms'] for e in ends))
    if ends and ui['worst_p95_ms'] > ui_p95_ms:
        errors.append(f"UI interval p95 {ui['worst_p95_ms']} ms > {ui_p95_ms} ms")
    if ui['max_ms'] > ui_max_ms:
        errors.append(f"UI interval max {ui['max_ms']} ms > {ui_max_ms} ms")
    submit = stats(submits)
    if submits and submit['p95'] > submit_p95_ms:
        errors.append(f"input-to-submit p95 {submit['p95']} ms > {submit_p95_ms} ms")
    trips = dict(turn_to_reply=stats(turns), ack_to_state=stats(acks))
    for name, value in trips.items():
        if value['count'] and value['p95'] > round_trip_p95_ms:
            errors.append(f"{name} p95 {value['p95']} ms > {round_trip_p95_ms} ms")

    memory = {}
    if len(ends) > WARMUP_SESSIONS:
        base = ends[WARMUP_SESSIONS]
        for key in ('free_internal', 'free_psram'):
            low = min(e[key] for e in ends[WARMUP_SESSIONS:])
            change = (low - base[key]) / base[key] * 100
            memory[key.replace('free_', '') + '_change_pct'] = round(change, 2)
            if change < -memory_pct:
                errors.append(f'{key} fell {-change:.1f}% below the post-warm-up baseline')
        memory.update(baseline=dict(free_internal=base['free_internal'], free_psram=base['free_psram']),
                      last=dict(free_internal=ends[-1]['free_internal'], free_psram=ends[-1]['free_psram']),
                      min_free_internal=min(e['min_free_internal'] for e in ends))

    uploads = [e for e in events if e.get('event') == 'investigation_upload']
    captures = dict(uploaded=sum(u['ok'] for u in uploads), failed=sum(not u['ok'] for u in uploads))
    if captures['failed']:
        errors.append(f"{captures['failed']} capture uploads failed")

    enough = len(taps) >= min_inputs and len(ends) > WARMUP_SESSIONS
    status = 'fail' if errors else 'pass' if enough else 'inconclusive'
    return dict(status=status, errors=errors, sessions=dict(ended=len(ends), end_states=dict(end_states)),
                input_events=len(taps), ui=ui, input_to_submit_ms=submit, round_trip_ms=trips,
                memory=memory, captures=captures,
                scope='Console taps through the LVGL click handlers (no touch controller); LVGL 20 ms probe-timer '
                      'intervals; mock provider; round trips on the device clock.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path, help='capture_serial output directory')
    args = parser.parse_args()
    events = [json.loads(line) for line in (args.run / 'events.jsonl').read_text().splitlines()]
    result = assess(events)
    summary = json.loads((args.run / 'summary.json').read_text())
    if any(summary.get(key) for key in ('integrity_errors', 'capture_errors', 'incomplete_captures')):
        result['errors'].append('run/capture integrity failed')
        result['status'] = 'fail'
    with (args.run / 'session-run.json').open('x') as output:
        json.dump(result, output, indent=2)
        output.write('\n')
    print(json.dumps(result, indent=2))
    if result['status'] != 'pass':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
