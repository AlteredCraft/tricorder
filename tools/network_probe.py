"""Measure fresh challenge/echo round trips to a diagnostic on the local LAN."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import time
from urllib.request import Request, build_opener, ProxyHandler


def validate_echo(response, nonce, boot_id):
    if not isinstance(response, dict) or response.get('nonce') != nonce:
        raise ValueError('echo nonce mismatch')
    if response.get('boot_id') != boot_id:
        raise ValueError('echo boot mismatch')
    if type(response.get('device_us')) is not int or response['device_us'] < 0:
        raise ValueError('invalid device timestamp')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--boot-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--count', type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.count <= 100:
        parser.error('--count must be 1..100')
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/'manifest.json').write_text(json.dumps({
        'spec_id':'G-0001.01', 'created_utc':datetime.now(timezone.utc).isoformat(),
        'url':args.url, 'expected_boot_id':args.boot_id, 'requested_count':args.count,
        'clock':'Host time.monotonic_ns for RTT; device timestamp is not subtracted.'}, indent=2)+'\n')
    opener = build_opener(ProxyHandler({}))
    records = []
    with (args.output/'events.jsonl').open('x') as out:
        for index in range(args.count):
            nonce = secrets.token_hex(16)
            record = {'index':index, 'nonce':nonce, 'host_start_ns':time.monotonic_ns()}
            try:
                request = Request(args.url.rstrip('/')+'/echo', data=nonce.encode(),
                                  headers={'Content-Type':'text/plain'}, method='POST')
                with opener.open(request, timeout=5) as response:
                    payload = response.read(4097)
                    if len(payload) > 4096:
                        raise ValueError('oversized echo')
                    record['response'] = json.loads(payload)
                    validate_echo(record['response'], nonce, args.boot_id)
                record['status'] = 'pass'
            except Exception as error:
                record.update(status='fail', error=f'{type(error).__name__}: {error}')
            record['host_end_ns'] = time.monotonic_ns()
            record['rtt_ms'] = (record['host_end_ns']-record['host_start_ns'])/1e6
            records.append(record)
            out.write(json.dumps(record)+'\n')
            out.flush()
    summary = {'status':'pass' if all(r['status']=='pass' for r in records) else 'fail',
               'count':len(records), 'successful_count':sum(r['status']=='pass' for r in records),
               'rtt_ms':[r['rtt_ms'] for r in records if r['status']=='pass'],
               'scope':'Isolated LAN echo only; no streaming or agent latency claim.'}
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))
    if summary['status'] != 'pass':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
