"""End-of-turn to first sound, by stage, for spoken-guidance turns (G-0001.04 C4).

All on the device clock. A turn ends when the device starts uploading the
capture that closes it (the person has finished recording). Stages: upload
(uploading -> capture_end sent), reply (turn sent -> ack sent, i.e. the Mac's
model reply arrived), then speak request, then first audio (first_audio_ms of
the speech event, measured from the speak request). Target: p95 <= 2.5 s from
the end of the turn, >= 30 turns.
"""
import argparse
import json
from pathlib import Path

from tools.session_run_evidence import stats


def assess(events, *, target_ms=2500, min_turns=30):
    turns, current = [], None
    for e in events:
        kind, message = e.get('event'), e.get('message_type')
        if kind == 'investigation_state' and e.get('state') == 'uploading':
            current = dict(upload=e['device_us'])
        elif current is None:
            continue
        elif kind == 'investigation_transport' and message in ('capture_end', 'turn', 'ack', 'speak'):
            current.setdefault(message, e['device_us'])
        elif kind == 'investigation_speech' and 'speak' in current and e.get('first_audio_ms', -1) >= 0:
            sound = current['speak'] + e['first_audio_ms'] * 1000
            if all(k in current for k in ('capture_end', 'turn', 'ack')):
                turns.append(dict(end_of_turn=(sound - current['upload']) / 1000,
                                  after_upload=(sound - current['capture_end']) / 1000,
                                  upload=(current['capture_end'] - current['upload']) / 1000,
                                  reply=(current['ack'] - current['turn']) / 1000,
                                  speak_request=(current['speak'] - current['ack']) / 1000,
                                  first_audio=e['first_audio_ms']))
            current = None
    errors = []
    whole = stats([t['end_of_turn'] for t in turns])
    if turns and whole['p95'] > target_ms:
        errors.append(f"end-of-turn to first sound p95 {whole['p95']} ms > {target_ms} ms")
    status = 'fail' if errors else 'pass' if len(turns) >= min_turns else 'inconclusive'
    return dict(status=status, errors=errors, turns=len(turns), end_of_turn_to_sound_ms=whole,
                after_upload_to_sound_ms=stats([t['after_upload'] for t in turns]),
                stages_ms={k: stats([t[k] for t in turns]) for k in ('upload', 'reply', 'speak_request', 'first_audio')},
                scope='SD replay turns (saved captures re-uploaded), live text model, Mac TTS, muted device playback.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path, help='capture_serial output directory')
    args = parser.parse_args()
    events = [json.loads(line) for line in (args.run / 'events.jsonl').read_text().splitlines()]
    result = assess(events)
    with (args.run / 'turn-timing.json').open('x') as output:
        json.dump(result, output, indent=2)
        output.write('\n')
    print(json.dumps(result, indent=2))
    if result['status'] != 'pass':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
