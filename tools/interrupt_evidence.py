"""Assess controlled SD-save interruptions (G-0001.05 C4).

Each trial is one serial run: the device restarted during a save
(storage_interrupt, then a new boot). The interrupted capture must not be
served by the device (neither .raw nor .json), and captures finished earlier
must still download with matching size and SHA-256. The device serves only
published .raw/.json names; an interrupted save stays a .part file.
"""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import build_opener, ProxyHandler

REQUIRED = 10


def assess(runs, device, finished_ids):
    errors, interrupted = [], []
    for events in runs:
        boots = [e for e in events if e.get('event') == 'boot']
        hit = next((i for i, e in enumerate(events) if e.get('event') == 'storage_interrupt'), None)
        if hit is None or not any(e.get('event') == 'boot' for e in events[hit:]) or len(boots) < 2:
            continue
        saving = [e for e in events[:hit] if e.get('event') == 'storage_resources' and e.get('phase') == 'before_archive']
        if saving:
            interrupted.append(saving[-1]['capture_id'])
    served = []
    for capture_id in interrupted:
        for suffix in ('.raw', '.json'):
            try:
                device.get(capture_id + suffix)
                served.append(capture_id + suffix)
            except FileNotFoundError:
                pass
    if served:
        errors.append(f'interrupted captures served: {served}')
    verified = 0
    for capture_id in finished_ids:
        try:
            meta = json.loads(device.get(capture_id + '.json'))
            raw = device.get(capture_id + '.raw')
        except FileNotFoundError:
            errors.append(f'finished capture missing: {capture_id}')
            continue
        if len(raw) != meta.get('size_bytes') or hashlib.sha256(raw).hexdigest() != meta.get('sha256'):
            errors.append(f'finished capture changed: {capture_id}')
            continue
        verified += 1
    status = 'fail' if errors else 'pass' if len(interrupted) >= REQUIRED else 'inconclusive'
    return dict(status=status, errors=errors, interruptions=len(interrupted), interrupted_ids=interrupted,
                served_incomplete=len(served), finished_verified=verified,
                scope='Software restarts during SD saves (not power loss).')


class Device:
    def __init__(self, url):
        self.url = url.rstrip('/')
        self.opener = build_opener(ProxyHandler({}))

    def get(self, name):
        try:
            with self.opener.open(f'{self.url}/test-file/{name}', timeout=20) as response:
                return response.read(1152001)
        except HTTPError as error:
            if error.code == 404:
                raise FileNotFoundError(name) from None
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True, help='http://DEVICE_IP')
    parser.add_argument('--runs', type=Path, nargs='+', required=True, help='capture_serial directories, one per trial')
    parser.add_argument('--finished', nargs='+', required=True, help='capture IDs saved before the trials')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    runs = [[json.loads(line) for line in (run / 'events.jsonl').read_text().splitlines()] for run in args.runs]
    result = assess(runs, Device(args.url), args.finished)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    if result['status'] != 'pass':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
