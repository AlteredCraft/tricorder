"""Verify live ingress hashes, sample ranges, clipping and independently derived speech."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from tools.audio_ingress_evidence import assess_ingress
from tools.inspect_capture import load_verified
from tools.speech_evidence import speech_reference


def compare_live(meta,raw,derived,speech):
    errors=[];blocks=meta.get('ingress_blocks',[]);frames=meta.get('frames')
    if (type(frames) is not int or frames<=0 or len(raw)!=frames*8
            or meta.get('format')!='pcm_s16le' or meta.get('channels')!=4
            or meta.get('sample_rate_hz')!=48000):
        return {'status':'fail','errors':['Invalid raw format/extent']}
    if meta.get('driver_epoch_integrity') is not True:errors.append('Driver epoch integrity not established')
    samples=struct.unpack('<'+'h'*(frames*4),raw)
    offset=0;last_read=meta.get('acquisition_start_us',-1);compute=0;durations=[];ready_delays=[]
    clipped=[0,0,0,0]
    for block in blocks:
        count=block.get('frames');read=block.get('read_end_us');duration=block.get('speech_compute_us')
        ready=block.get('speech_ready_us')
        if (type(count) is not int or count<=0 or count>1024 or block.get('source_start_frame')!=offset
                or offset+count>frames or type(read) is not int or type(duration) is not int or duration<0
                or type(ready) is not int or ready<read or ready-read<duration
                or read<last_read or ready>meta.get('acquisition_end_us',-1)):
            errors.append('Invalid ingress extent/timing');break
        chunk=raw[offset*8:(offset+count)*8]
        if hashlib.sha256(chunk).hexdigest()!=block.get('sha256') or block.get('raw_unchanged') is not True:
            errors.append('Ingress hash/mutation mismatch')
        actual=[sum(x in (-32768,32767) for x in samples[offset*4+slot:(offset+count)*4:4]) for slot in range(4)]
        if actual!=block.get('clipped_samples'):errors.append('Raw clipping mismatch')
        clipped=[a+b for a,b in zip(clipped,actual)]
        last_read=ready;compute+=duration;durations.append(duration);ready_delays.append(ready-read);offset+=count
    if offset!=frames:errors.append('Incomplete ingress ranges')
    expected={'boot_id':meta.get('boot_id'),'source_capture_id':meta.get('capture_id'),'source_slot':0,
              'source_start_frame':0,'source_frames':frames,'format':'pcm_s16le','role':'speech_live',
              'channels':1,'sample_rate_hz':16000,'processing':'dc80-fir63-fc6500-decimate3-v1',
              'compute_us':compute,'frames':frames//3,'input_clipped':clipped[0]}
    for key,value in expected.items():
        if value is None or derived.get(key)!=value:errors.append('Derived '+key+' mismatch')
    output,output_clipped=speech_reference(samples[::4],True,with_clipping=True)
    if derived.get('output_clipped')!=output_clipped:errors.append('Derived output clipping mismatch')
    maximum=None
    if len(speech)!=len(output)*2:errors.append('Wrong derived byte count')
    else:
        actual=struct.unpack('<'+'h'*len(output),speech)
        maximum=max((abs(a-b) for a,b in zip(actual,output)),default=0)
        if maximum>2:errors.append('Derived PCM differs from independent reference')
    return {'status':'fail' if errors else 'pass','capture_id':meta.get('capture_id'),'errors':errors,
            'blocks':len(blocks),'frames':frames,'max_sample_error_counts':maximum,
            'raw_clipped_samples':clipped,'speech_compute_us':durations,'read_complete_to_speech_ready_us':ready_delays}


def assess_live_run(run):
    captures={};raw_captures={}
    for path in (run/'captures').glob('*.json'):
        meta=json.loads(path.read_text())
        if meta.get('role')=='speech_live' or 'driver_epoch_integrity' in meta:
            meta,data=load_verified(path);captures[meta['capture_id']]=(meta,data)
            if 'driver_epoch_integrity' in meta:raw_captures[meta['capture_id']]=(meta,len(data))
    events=[json.loads(line) for line in (run/'events.jsonl').read_text().splitlines()]
    ingress=assess_ingress(events,raw_captures)
    errors=[];pairs=[];seen=set()
    for meta,data in captures.values():
        if meta.get('role')!='speech_live':continue
        source=meta.get('source_capture_id')
        if source not in raw_captures or source in seen:errors.append('Missing/duplicate raw source');continue
        seen.add(source);raw_meta,raw=captures[source]
        pairs.append(compare_live(raw_meta,raw,meta,data))
    if seen!=set(raw_captures) or not pairs:errors.append('Not every raw capture has one speech derivative')
    if ingress['status']!='pass':errors.append('Ingress assessment failed')
    summary=json.loads((run/'summary.json').read_text())
    if any(summary.get(key) for key in ('integrity_errors','capture_errors','incomplete_captures')):
        errors.append('Run/capture integrity failed')
    return {'status':'fail' if errors or any(p['status']!='pass' for p in pairs) else 'pass',
            'errors':errors,'ingress':ingress,'pairs':pairs,
            'scope':'Isolated synchronous live capture; no physical mapping, SD or combined-load acceptance.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run',type=Path)
    args=parser.parse_args();result=assess_live_run(args.run)
    with (args.run/'live-audio.json').open('x') as output:
        json.dump(result,output,indent=2);output.write('\n')
    print(json.dumps(result,indent=2))
    if result['status']!='pass':raise SystemExit(1)


if __name__=='__main__':main()
