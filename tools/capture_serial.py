"""Capture a bounded serial run, retaining raw output and strict evidence summaries."""
import argparse
import json
import os
import re
import signal
import time
from datetime import datetime, timezone
from pathlib import Path

from tools.evidence import assess, parse_event
from tools.captures import CaptureStore
from tools.session_driver import SessionDriver


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seconds', type=float, default=30)
    parser.add_argument('--reset', action='store_true')
    parser.add_argument('--replay-session', help='After reset/SD/network readiness, replay this saved ab-<32 lowercase hex> session; no new acquisition')
    parser.add_argument('--replay-count', type=int, default=1, help='Replay the saved session this many times, each after the previous one ends (G-0001.02 baselines)')
    parser.add_argument('--console-command', help='Send this console line once, after SD/network readiness (e.g. TRICORDER_POWER_STEPS)')
    parser.add_argument('--drive-sessions', type=int, help='Run this many guided sessions by console taps (tools/session_driver.py)')
    parser.add_argument('--drive-replay', help='Driven sessions are SD replays of this saved session')
    parser.add_argument('--tap-delay-s', type=float, default=1.0)
    parser.add_argument('--cancel-at', help='Tap Cancel when a session reaches this state')
    parser.add_argument('--cancel-delay-s', type=float, default=1.0)
    parser.add_argument('--pause-at', help='Pause the service (SIGSTOP) when a session reaches this state')
    parser.add_argument('--pause-s', type=float, default=10.0)
    parser.add_argument('--pause-every', type=int, default=1, help='Pause in every Nth session')
    parser.add_argument('--pause-count', type=int, help='Pause at most this many times')
    parser.add_argument('--service-pid', type=int, help='Service process to pause and resume')
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
    driver=None
    if args.drive_sessions is not None:
        if args.replay_session or not args.reset or (args.pause_at and not args.service_pid):
            parser.error('--drive-sessions needs --reset, excludes --replay-session, and --pause-at needs --service-pid')
        if args.drive_replay and not re.fullmatch(r'ab-[0-9a-f]{32}',args.drive_replay):
            parser.error('--drive-replay needs a saved ab-<32 hex> session')
        try:
            driver=SessionDriver(args.drive_sessions,replay=args.drive_replay,delay_s=args.tap_delay_s,
                                 cancel_at=args.cancel_at,cancel_delay_s=args.cancel_delay_s,pause_at=args.pause_at,
                                 pause_s=args.pause_s,pause_every=args.pause_every,pause_count=args.pause_count)
        except ValueError as error:
            parser.error(str(error))
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
    if driver:
        manifest.update(driven_sessions=args.drive_sessions,drive_replay=args.drive_replay,tap_delay_s=args.tap_delay_s,
                        cancel_at=args.cancel_at,cancel_delay_s=args.cancel_delay_s,pause_at=args.pause_at,
                        pause_s=args.pause_s,pause_every=args.pause_every,pause_count=args.pause_count,
                        input_scope='USB console taps through the LVGL click handlers; no touch controller')
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
    if args.replay_session or driver or args.console_command:port.write_timeout=2
    console_sent=False
    driven_boot=None;host_actions=[]
    def perform(action):
        kind,argument=action
        if kind in ('pause','resume'):
            os.kill(args.service_pid,signal.SIGSTOP if kind=='pause' else signal.SIGCONT)
            host_actions.append({'action':'service_'+kind,'host_ns':time.monotonic_ns()});return
        command=(f'TRICORDER_TAP {argument}\n' if kind=='tap' else f'TRICORDER_REPLAY {argument}\n').encode()
        if port.write(command)!=len(command):raise OSError('short console command write')
        port.flush()
    try:
        port.open()
        with port, (args.output/'serial.log').open('xb') as raw, (args.output/'events.jsonl').open('x') as out:
            if args.reset:
                HardReset(port, uses_usb=True)()
            end = time.monotonic() + args.seconds
            pending = b''
            while time.monotonic() < end and not (args.stop_file and args.stop_file.exists()) and not (
                    args.replay_count>1 and replays_ended==args.replay_count) and not (driver and driver.done):
                if driver:
                    for action in driver.due():perform(action)
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
                        if args.console_command and not console_sent and event['event']=='check' \
                                and event.get('check')=='storage_http':
                            command=(args.console_command+'\n').encode()
                            if port.write(command)!=len(command):raise OSError('short console command write')
                            port.flush();console_sent=True
                        if driver:
                            # Only the boot this run reset into drives sessions.
                            if event['event']=='boot' and driven_boot is None:driven_boot=event['boot_id']
                            if event['boot_id']==driven_boot:driver.on_event(event)
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
    if driver:
        if driver.resume_due is not None:
            try:os.kill(args.service_pid,signal.SIGCONT)
            except OSError:pass
        summary['driver']=driver.summary()
        summary['host_actions']=host_actions
        if driver.ended<driver.sessions:errors.append(f'{driver.ended} of {driver.sessions} driven sessions ended')
    if errors:
        summary['status'] = 'fail'
    (args.output/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary, indent=2))
    if summary['status'] == 'fail':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
