"""Independently check isolated I2S epochs against verified saved PCM."""
import argparse
import json
from pathlib import Path
from tools.inspect_capture import load_verified

COUNTERS=('read_bytes','dma_bytes','overwritten_bytes','overflows','short_reads','read_errors')


def assess_ingress(events,captures):
    records=[event for event in events if event.get('event')=='audio_ingress']
    errors=[];results=[];seen=set();previous={}
    for record in records:
        capture_id=record.get('capture_id');boot=record.get('boot_id')
        problems=[]
        if not isinstance(capture_id,str) or not isinstance(boot,str) or capture_id in seen:
            errors.append('Missing/duplicate capture identity');continue
        seen.add(capture_id)
        keys=[counter+'_'+edge for counter in COUNTERS for edge in ('before','after')]
        keys+=['requested_bytes','acquisition_start_us','acquisition_end_us']
        if any(type(record.get(key)) is not int or record[key]<0 for key in keys):
            errors.append(capture_id+': missing or invalid integer counters/timestamps');continue
        start=record['acquisition_start_us'];end=record['acquisition_end_us']
        if end<=start or record['requested_bytes']<=0:problems.append('Invalid acquisition extent')
        delta={counter:record[counter+'_after']-record[counter+'_before'] for counter in COUNTERS}
        if any(value<0 for value in delta.values()):problems.append('Counter regressed within epoch')
        prior=previous.get(boot)
        if prior and (start<prior['acquisition_end_us'] or any(record[c+'_before']<prior[c+'_after'] for c in COUNTERS)):
            problems.append('Lifetime counters or epoch time regressed')
        previous[boot]=record
        if delta['read_bytes']!=record['requested_bytes'] or delta['dma_bytes']<delta['read_bytes']:
            problems.append('Read/production totals do not account for requested bytes')
        if any(delta[counter]!=0 for counter in COUNTERS[2:]):problems.append('Loss, short read or read error within epoch')
        saved=captures.get(capture_id)
        if saved is None:problems.append('Missing verified PCM capture')
        else:
            meta,size=saved
            expected={'boot_id':boot,'capture_id':capture_id,'format':'pcm_s16le','channels':4,
                      'sample_rate_hz':48000,'acquisition_start_us':start,'acquisition_end_us':end}
            if any(meta.get(key)!=value for key,value in expected.items()):problems.append('Capture identity/format/range mismatch')
            if meta.get('driver_epoch_integrity') is not True:problems.append('Firmware epoch integrity not established')
            frames=meta.get('frames')
            if type(frames) is not int or frames<=0 or frames*8!=size or size!=record['requested_bytes']:
                problems.append('Capture frame/byte totals mismatch')
        errors.extend(capture_id+': '+problem for problem in problems)
        results.append({'capture_id':capture_id,'status':'fail' if problems else 'pass',
                        'duration_us':end-start,'counter_deltas':delta})
    return {'status':'fail' if errors else ('pass' if records else 'inconclusive'),
            'errors':errors,'epochs':results,
            'scope':'Observed IDF RX epochs only; no physical channel, clock accuracy, live block-hash or combined-load acceptance.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run',type=Path)
    args=parser.parse_args()
    events=[json.loads(line) for line in (args.run/'events.jsonl').read_text().splitlines()]
    captures={}
    for path in (args.run/'captures').glob('*.json'):
        meta=json.loads(path.read_text())
        if 'driver_epoch_integrity' in meta:
            meta,data=load_verified(path)
            captures[meta['capture_id']]=(meta,len(data))
    result=assess_ingress(events,captures)
    summary=json.loads((args.run/'summary.json').read_text())
    if any(summary.get(key) for key in ('integrity_errors','capture_errors','incomplete_captures')):
        result['errors'].append('Run/capture integrity failed');result['status']='fail'
    with (args.run/'audio-ingress.json').open('x') as output:
        json.dump(result,output,indent=2);output.write('\n')
    print(json.dumps(result,indent=2))
    if result['status']!='pass':raise SystemExit(1)


if __name__=='__main__':main()
