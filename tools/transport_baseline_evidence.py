"""G-0001.02 C1: capture upload and spoken-guidance playback baselines.

Reads one serial run of repeated SD replays (capture_serial --replay-count) and,
optionally, the replay service's output directory. Upload and playback never
overlap in a session, so each stream's counters come from its own events:
upload (captures and chunks sent, consumed = hash-acknowledged by the Mac,
dropped = failed) and playback (frames produced by the Mac, received and played
by the device, underruns). Each stream needs 60 s of activity to pass.
"""
import argparse
import json
from pathlib import Path

CHUNK_BYTES = 4096
SPEECH_RATE_HZ = 24000
REQUIRED_S = 60


def assess(events, host_speech=None):
    errors = []
    boots = {e.get('boot_id') for e in events if e.get('event') == 'boot'}
    if len(boots) > 1:
        errors.append('device reset during the baseline')
    uploads = [e for e in events if e.get('event') == 'investigation_upload']
    speeches = [e for e in events if e.get('event') == 'investigation_speech']
    ends = [e for e in events if e.get('event') == 'investigation_end']

    consumed = [u for u in uploads if u.get('ok') is True]
    if len(consumed) != len(uploads):
        errors.append(f'{len(uploads) - len(consumed)} capture uploads failed')
    for u in consumed:
        if u['chunks'] != -(-u['bytes'] // CHUNK_BYTES):
            errors.append(f"{u['capture_id']}: {u['chunks']} chunks for {u['bytes']} bytes")
    active_us = sum(u['upload_us'] for u in consumed)
    upload = dict(captures=len(uploads), consumed=len(consumed), dropped=len(uploads) - len(consumed),
                  chunks_sent=sum(u['chunks'] for u in uploads), bytes=sum(u['bytes'] for u in consumed),
                  active_s=active_us / 1e6,
                  throughput_kib_s=sum(u['bytes'] for u in consumed) / 1024 / (active_us / 1e6) if active_us else None,
                  max_upload_s=max((u['upload_us'] for u in consumed), default=0) / 1e6,
                  max_chunk_ms=max((u['max_chunk_us'] for u in uploads), default=0) / 1000)

    for s in speeches:
        problems = [name for name, bad in (
            ('not complete', s['status'] != 'complete'), ('speaker not open', not s['speaker_open']),
            ('stopped', s['stopped']), ('underruns', s['underruns']),
            ('unplayed frames', s['played_frames'] != s['frames'])) if bad]
        if problems:
            errors.append(f"{s['request_id']}: " + ', '.join(problems))
    received = sum(s['frames'] for s in speeches)
    played = sum(s['played_frames'] for s in speeches)
    playback = dict(requests=len(speeches), frames_received=received, frames_played=played,
                    dropped_frames=received - played, underruns=sum(s['underruns'] for s in speeches),
                    played_s=played / SPEECH_RATE_HZ,
                    max_first_audio_ms=max((s['first_audio_ms'] for s in speeches), default=None))
    if host_speech is not None:
        produced = [h['frames'] for h in host_speech]
        playback['frames_produced'] = sum(produced)
        if sorted(produced) != sorted(s['frames'] for s in speeches):
            errors.append('Mac speech frames do not match what the device received')

    replays = dict(ended=len(ends), complete=sum(e.get('state') == 'complete' for e in ends))
    if replays['complete'] != replays['ended']:
        errors.append(f"{replays['ended'] - replays['complete']} replays did not complete")

    short = [name for name, seconds in (('upload', upload['active_s']), ('playback', playback['played_s']))
             if seconds < REQUIRED_S]
    status = 'fail' if errors else 'inconclusive' if short else 'pass'
    return dict(status=status, errors=errors, short_of_60_s=short, upload=upload, playback=playback,
                replays=replays,
                scope='SD replay: saved captures uploaded and replayed guidance spoken, one stream at a time; '
                      'no microphone, camera or operator.')


def host_speech_records(service_dir):
    records = []
    for path in sorted(Path(service_dir).glob('*/transcript.jsonl')):
        for line in path.read_text().splitlines():
            message = json.loads(line).get('message', {})
            if message.get('type') == 'speech_output':
                records.append(message)
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path, help='capture_serial output directory')
    parser.add_argument('--service', type=Path, help='replay service --output directory')
    args = parser.parse_args()
    events = [json.loads(line) for line in (args.run / 'events.jsonl').read_text().splitlines()]
    result = assess(events, host_speech_records(args.service) if args.service else None)
    summary = json.loads((args.run / 'summary.json').read_text())
    if any(summary.get(key) for key in ('integrity_errors', 'capture_errors', 'incomplete_captures')):
        result['errors'].append('run/capture integrity failed')
        result['status'] = 'fail'
    with (args.run / 'transport-baseline.json').open('x') as output:
        json.dump(result, output, indent=2)
        output.write('\n')
    print(json.dumps(result, indent=2))
    if result['status'] != 'pass':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
