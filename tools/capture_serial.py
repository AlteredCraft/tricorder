"""Capture a bounded serial run, retaining raw output and strict evidence summaries."""
import argparse
import json
import re
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
    parser.add_argument('--replay-session', help='After reset/SD/network readiness, replay this saved ab-<32 lowercase hex> session; no new acquisition')
    parser.add_argument('--replay-count', type=int, default=1, help='Replay the saved session this many times, each after the previous one ends (G-0001.02 baselines)')
    parser.add_argument('--observation-boot', help='Observe this existing boot without claiming startup or continuity before attachment')
    parser.add_argument('--stop-file', type=Path, help='Finish and summarize when this file appears')
    parser.add_argument('--checks', nargs='*', default=[])
    parser.add_argument('--spec-id', default='G-0001.01')
    parser.add_argument('--spec-revision', help='Exact dated revision of the owning spec')
    parser.add_argument('--workload', help='Actual active streams, overlap and fixture scope')
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error('--seconds must be positive')
    if args.observation_boot and args.reset:
        parser.error('--observation-boot cannot be combined with --reset')
    if args.replay_session and (not re.fullmatch(r'ab-[0-9a-f]{32}',args.replay_session) or
                               not args.reset or args.spec_id not in ('G-0002.01','G-0001.02')):
        parser.error('--replay-session requires a valid saved session, --reset and --spec-id G-0002.01 or G-0001.02')
    if not 1<=args.replay_count<=50 or (args.replay_count>1 and not args.replay_session):
        parser.error('--replay-count is 1 to 50 and needs --replay-session')
    if (args.spec_id != 'G-0001.01' or args.spec_revision or args.workload) and not (
            args.spec_revision and args.spec_revision.strip() and args.workload and args.workload.strip()):
        parser.error('explicit spec metadata requires both --spec-revision and --workload')
    import serial
    from esptool.reset import HardReset
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = {'spec_id': args.spec_id, 'spec_revision': args.spec_revision,
                'workload': args.workload, 'run_id': args.output.name,
                'created_utc': datetime.now(timezone.utc).isoformat(),
                'port': args.port, 'requested_duration_s': args.seconds,
                'host_clock': 'time.monotonic_ns; never subtract from device_us',
                'device_clock': 'esp_timer_get_time microseconds since boot',
                'required_checks': args.checks, 'reset_requested': args.reset,
                'observation_boot': args.observation_boot}
    if args.replay_session:
        manifest.update(replay=True,source_session_id=args.replay_session,replay_count=args.replay_count,
                        replay_scope='SD transport replay; no new sensor acquisition')
    (args.output/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    events, errors = [], []
    # --reset interrupts the previous firmware mid-line; such lines precede our
    # first boot event and are counted, not treated as this run's evidence.
    seen_boot, pre_reset_discarded = not args.reset, 0
    replay_boot=None;replay_sd=replay_network=replay_http=False;replay_state=None
    replays_sent=replays_ended=replays_completed=0
    captures = CaptureStore(args.output/'captures')
    port = serial.Serial()
    port.port, port.baudrate, port.timeout = args.port, 115200, .2
    port.dtr, port.rts = False, False
    if args.replay_session:port.write_timeout=2
    try:
        port.open()
        with port, (args.output/'serial.log').open('xb') as raw, (args.output/'events.jsonl').open('x') as out:
            if args.reset:
                HardReset(port, uses_usb=True)()
            end = time.monotonic() + args.seconds
            pending = b''
            while time.monotonic() < end and not (args.stop_file and args.stop_file.exists()) and not (
                    args.replay_count>1 and replays_ended==args.replay_count):
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
                        if seen_boot:errors.append(str(error))
                        else:pre_reset_discarded+=1
                        continue
                    if event is not None and event['event']=='boot':seen_boot=True
                    if event is not None:
                        event['host_receipt_ns'] = received
                        events.append(event)
                        out.write(json.dumps(event)+'\n')
                        out.flush()
                        if args.replay_session:
                            if event['event']=='boot':
                                replay_boot=event['boot_id'];replay_sd=replay_network=replay_http=False
                            if event['boot_id']==replay_boot:
                                if event['event']=='storage_ready':replay_sd=event.get('mounted') is True
                                if event['event']=='wifi_address':replay_network=True
                                if event['event']=='check' and event.get('check')=='storage_http':replay_http=event.get('result')=='pass'
                                if event['event']=='investigation_state' and event.get('session_id')==args.replay_session:
                                    replay_state=event.get('state')
                                if event['event']=='investigation_end' and event.get('session_id')==args.replay_session:
                                    replays_ended+=1;replays_completed+=event.get('state')=='complete'
                                # The next replay starts only after the previous one ended complete.
                                if replay_sd and replay_network and replay_http and replays_sent<args.replay_count and \
                                        replays_ended==replays_sent==replays_completed:
                                    command=('TRICORDER_REPLAY '+args.replay_session+'\n').encode()
                                    if port.write(command)!=len(command):raise OSError('short replay command write')
                                    port.flush();replays_sent+=1
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
    if pre_reset_discarded:summary['pre_reset_lines_discarded']=pre_reset_discarded
    if args.replay_session:
        summary.update(replay=True,replay_command_sent=replays_sent>0,replay_state=replay_state,
                       replays_sent=replays_sent,replays_completed=replays_completed)
        if not replays_sent or replay_state!='complete':errors.append('SD replay did not reach complete in this collection window')
        if args.replay_count>1 and replays_completed<args.replay_count:
            errors.append(f'{replays_completed} of {args.replay_count} SD replays completed')
    if errors:
        summary['status'] = 'fail'
    (args.output/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary, indent=2))
    if summary['status'] == 'fail':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
