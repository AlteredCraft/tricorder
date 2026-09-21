"""Assess one expected queued-JPEG panic, never normal workload acceptance."""
import argparse
import json
from pathlib import Path

from tools.evidence import assess, parse_event

GUARD_REASON='JPEG DMA ownership unresolved: refusing error-path release'
DRIVER_TIMEOUT='jpeg-dma2d handle jpeg decode timeout'


def assess_timeout(serial_text):
    events=[];positions=[];errors=[]
    lines=serial_text.splitlines()
    for index,line in enumerate(lines):
        try:
            event=parse_event(line.strip())
        except ValueError as error:
            errors.append(str(error));continue
        if event is not None:
            events.append(event);positions.append(index)
    integrity=assess(events,[])
    errors.extend(integrity['integrity_errors'])
    boots=[(i,e) for i,e in zip(positions,events) if e['event']=='boot']
    guards=[i for i,s in enumerate(lines) if GUARD_REASON in s]
    timeouts=[i for i,s in enumerate(lines) if DRIVER_TIMEOUT in s]
    def checks(name):
        return [(i,e) for i,e in zip(positions,events)
                if e['event']=='check' and e['check']==name]
    armed=checks('jpeg_timeout_fixture_armed');skipped=checks('jpeg_timeout_fixture_skipped')
    if len(boots)!=2: errors.append('Expected exactly two complete boot identities')
    if len(guards)!=1 or len(timeouts)!=1: errors.append('Expected exactly one driver timeout and guard panic')
    if len(armed)!=1 or len(skipped)!=1: errors.append('Expected one arming and one skipped rearming')
    if len(boots)==2 and len(guards)==len(timeouts)==len(armed)==len(skipped)==1:
        first,second=boots
        if not first[0]<armed[0][0]<timeouts[0]<guards[0]<second[0]<skipped[0][0]:
            errors.append('Arming, timeout, guard and panic reboot are out of order')
        if second[1].get('reset_reason')!=4: errors.append('Second boot is not ESP_RST_PANIC')
        if not first[1].get('firmware') or first[1].get('firmware')!=second[1].get('firmware'):
            errors.append('Firmware identity missing or changed between boots')
        for row,boot in ((armed[0],first),(skipped[0],second)):
            if row[1]['boot_id']!=boot[1]['boot_id'] or row[1]['result']!='pass':
                errors.append('Fixture check failed or belongs to the wrong boot')
        initialized=[(i,e) for i,e in checks('jpeg_initialize') if e['boot_id']==second[1]['boot_id']]
        if len(initialized)!=1 or initialized[0][0]<=skipped[0][0] or initialized[0][1]['result']!='pass':
            errors.append('JPEG did not initialize after skipped rearming')
    if any(e['event']=='check' and e['result']=='fail' for e in events):
        errors.append('An instrumented device check failed')
    return {'status':'fail' if errors else 'pass','errors':errors,
            'boot_ids':[e['boot_id'] for _,e in boots], 'workload_acceptance':False,
            'scope':'Expected queued-timeout guard and panic reboot only; not recoverable timeout, memory-return, or combined-load acceptance.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run',type=Path)
    args=parser.parse_args()
    summary=json.loads((args.run/'summary.json').read_text()) # Require finalized collection.
    result=assess_timeout((args.run/'serial.log').read_text(errors='replace'))
    result['normal_run_status']=summary['status']
    if summary.get('integrity_errors') or summary.get('incomplete_captures'):
        result['errors'].append('Collector integrity/incomplete-capture errors')
        result['status']='fail'
    if any(GUARD_REASON not in error for error in summary.get('capture_errors',[])):
        result['errors'].append('Unexpected collector or panic error beyond the injected guard')
        result['status']='fail'
    with (args.run/'expected-fault-assessment.json').open('x') as output:
        json.dump(result,output,indent=2);output.write('\n')
    print(json.dumps(result,indent=2))
    if result['status']!='pass': raise SystemExit(1)


if __name__=='__main__': main()
