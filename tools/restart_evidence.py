"""Assess one complete ten-software-reset series; never count USB resets as software resets."""
import argparse
import json
from pathlib import Path

from tools.evidence import assess

REQUIRED_CHECKS = ('imu_id', 'imu_initialize', 'ina226_manufacturer', 'power_initialize',
                   'camera_driver_id', 'display_initialize', 'rtc_advance', 'camera_frame',
                   'audio_capture', 'wifi_initialize')


def assess_software_resets(events):
    integrity=assess(events, [])
    errors=list(integrity['integrity_errors'])
    boots={}
    for event in events:
        boots.setdefault(event['boot_id'], []).append(event)
    requested=[e for e in events if e['event']=='software_reset_requested']
    resumed=[e for e in events if e['event']=='software_reset_resumed']
    complete=[e for e in events if e['event']=='software_reset_complete']
    if len(boots)!=11 or len(requested)!=10 or len(resumed)!=10 or len(complete)!=1:
        errors.append('Expected initial boot, ten requested/resumed resets and one completion')
    if [e.get('cycle') for e in requested]!=list(range(1,11)) or [e.get('cycle') for e in resumed]!=list(range(1,11)):
        errors.append('Reset cycles must be exactly 1 through 10')
    series={e.get('series_id') for e in requested+resumed+complete}
    if len(series)!=1 or None in series:
        errors.append('Missing or mismatched series identity')
    firmware={items[0].get('firmware') for items in boots.values()}
    if len(firmware)!=1 or None in firmware:
        errors.append('Firmware identity changed or missing')
    boot_ids=list(boots)
    checks={}
    for index, item in enumerate(resumed):
        boot=item['boot_id']
        if index+1>=len(boot_ids) or boot!=boot_ids[index+1]:
            errors.append('Resumed reset does not correspond to the next unique boot')
        if boots[boot][0].get('reset_reason')!=3: # pinned IDF ESP_RST_SW
            errors.append(f'{boot}: reset reason is not ESP_RST_SW')
        if index>=len(requested) or requested[index]['boot_id']!=boot_ids[index]:
            errors.append('Reset request was not in the preceding boot')
        checked=assess(boots[boot],REQUIRED_CHECKS)
        checks[boot]=checked['checks']
        if checked['status']!='pass':
            errors.append(f'{boot}: required initialization evidence is incomplete or failed')
    if complete and (not resumed or complete[0]['boot_id']!=resumed[-1]['boot_id'] or complete[0].get('cycle')!=10):
        errors.append('Completion must be on reset boot ten')
    return {'status':'fail' if errors else 'pass','software_reset_boots':len(resumed),
            'checks':checks,'errors':errors,
            'scope':'Selected initialization checks only; no cold-start, SD, acoustic or full-goal acceptance.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run',type=Path)
    args=parser.parse_args()
    events=[json.loads(line) for line in (args.run/'events.jsonl').read_text().splitlines()]
    result=assess_software_resets(events)
    serial_summary=json.loads((args.run/'summary.json').read_text())
    if serial_summary.get('capture_errors') or serial_summary.get('integrity_errors') or serial_summary.get('incomplete_captures'):
        result['errors'].append('Serial/capture integrity failed; inspect original summary')
        result['status']='fail'
    with (args.run/'software-resets.json').open('x') as output:
        json.dump(result,output,indent=2)
        output.write('\n')
    print(json.dumps(result,indent=2))
    if result['status']!='pass': raise SystemExit(1)


if __name__=='__main__':main()
