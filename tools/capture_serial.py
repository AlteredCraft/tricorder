"""Capture a bounded serial run, retaining raw output and strict evidence summaries."""
import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from tools.evidence import assess, parse_event
from tools.captures import CaptureStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seconds', type=float, default=30)
    parser.add_argument('--reset', action='store_true')
    parser.add_argument('--observation-boot', help='Observe this existing boot without claiming startup or continuity before attachment')
    parser.add_argument('--stop-file', type=Path, help='Finish and summarize when this file appears')
    parser.add_argument('--checks', nargs='*', default=[])
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error('--seconds must be positive')
    if args.observation_boot and args.reset:
        parser.error('--observation-boot cannot be combined with --reset')
    import serial
    from esptool.reset import HardReset
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = {'spec_id': 'G-0001.01', 'run_id': args.output.name,
                'created_utc': datetime.now(timezone.utc).isoformat(),
                'port': args.port, 'requested_duration_s': args.seconds,
                'host_clock': 'time.monotonic_ns; never subtract from device_us',
                'device_clock': 'esp_timer_get_time microseconds since boot',
                'required_checks': args.checks, 'reset_requested': args.reset,
                'observation_boot': args.observation_boot}
    (args.output/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    events, errors = [], []
    captures = CaptureStore(args.output/'captures')
    port = serial.Serial()
    port.port, port.baudrate, port.timeout = args.port, 115200, .2
    port.dtr, port.rts = False, False
    try:
        port.open()
        with port, (args.output/'serial.log').open('xb') as raw, (args.output/'events.jsonl').open('x') as out:
            if args.reset:
                HardReset(port, uses_usb=True)()
            end = time.monotonic() + args.seconds
            pending = b''
            while time.monotonic() < end and not (args.stop_file and args.stop_file.exists()):
                chunk = port.read(8192)
                if not chunk:
                    continue
                received = time.monotonic_ns()
                raw.write(chunk)
                raw.flush()
                pending += chunk
                if len(pending) > 65536:
                    raise ValueError('serial line exceeded 64 KiB bound')
                while b'\n' in pending:
                    line, pending = pending.split(b'\n', 1)
                    decoded = line.decode('utf-8', errors='replace').strip()
                    if any(marker in decoded for marker in ('Guru Meditation', 'abort() was called', 'assert failed:', 'Task watchdog got triggered', 'JPEG DMA ownership unresolved:')):
                        errors.append(decoded)
                    try:
                        event = parse_event(decoded)
                    except ValueError as error:
                        errors.append(str(error))
                        continue
                    if event is not None:
                        event['host_receipt_ns'] = received
                        events.append(event)
                        out.write(json.dumps(event)+'\n')
                        out.flush()
                        try:
                            captures.consume(event)
                        except ValueError as error:
                            errors.append(str(error))
            if pending.startswith(b'TRICORDER '):
                errors.append('truncated instrumentation at end of capture')
    except Exception as error:
        errors.append(f'{type(error).__name__}: {error}')
    summary = assess(events, args.checks, observation_boot=args.observation_boot)
    summary['incomplete_captures'] = captures.close()
    if summary['incomplete_captures']:
        errors.append('unfinished captures retained as incomplete')
    summary['capture_errors'] = errors
    if errors:
        summary['status'] = 'fail'
    (args.output/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary, indent=2))
    if summary['status'] == 'fail':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
