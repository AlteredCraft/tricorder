"""Assess the bounded 60-second isolated audio/speech/FFT workload."""
import argparse
import json
from pathlib import Path
import struct
from tools.inspect_capture import load_verified


def distribution(values):
    values=sorted(values)
    return {'p50':values[(len(values)-1)//2],'p95':values[min(len(values)-1,(len(values)*95+99)//100-1)],'max':values[-1]}


def compare_baseline(meta,data):
    errors=[];missing=[]
    expected={'format':'audio_baseline_u32le','rows':6000,'columns':4,'sample_rate_hz':48000,
              'block_frames':480,'raw_channels':4,'speech_rate_hz':16000,'speech_frames':960000,
              'fft_frames':2048,'fft_hop_frames':2400,'fft_count':1200,'raw_frames':2880000,
              'read_bytes':23040000,'overflows':0,'overwritten_bytes':0,'short_reads':0,
              'read_errors':0,'raw_mutations':0}
    for key,value in expected.items():
        if key not in meta:missing.append(key)
        elif meta[key]!=value:errors.append(key+' mismatch')
    if 'dma_bytes' not in meta:missing.append('dma_bytes')
    elif type(meta['dma_bytes']) is not int or meta['dma_bytes']<23040000:errors.append('DMA production insufficient/invalid')
    if len(data)!=6000*16:return {'status':'fail','errors':errors+['Incomplete timing rows']}
    rows=list(struct.iter_unpack('<4I',data));previous=0;ready_delays=[];intervals=[];compute=[];fft_times=[]
    for index,(read,ready,duration,fft) in enumerate(rows):
        if read<=previous or ready<read or duration>ready-read or fft!=int((index+1)%5==0):
            errors.append('Timing/cadence mismatch at block '+str(index));break
        previous=ready;ready_delays.append(ready-read);compute.append(duration)
        if index:intervals.append(read-rows[index-1][0])
        if fft:fft_times.append(ready)
    total=meta.get('duration_us')
    if total is None:missing.append('duration_us')
    elif type(total) is not int or total<rows[-1][1] or total<=0:errors.append('Invalid acquisition duration')
    memory=meta.get('memory_samples',[])
    if len(memory)!=60:missing.append('memory samples at 100-block intervals')
    else:
        for second,sample in enumerate(memory,1):
            if sample.get('block_index')!=second*100 or any(type(sample.get(key)) is not int or sample[key]<=0 for key in
                    ('free_internal','free_psram','largest_internal','largest_psram','stack_margin_bytes')):
                errors.append('Invalid memory evidence');break
    cpu=[]
    before=meta.get('cpu_before',{});after=meta.get('cpu_after',{})
    if (type(before.get('total_ticks')) is not int or type(after.get('total_ticks')) is not int
            or not before.get('tasks') or not after.get('tasks')):missing.append('CPU runtime evidence')
    else:
        span=(after['total_ticks']-before['total_ticks']) & 0xffffffff
        if not span:errors.append('Invalid CPU runtime span')
        else:
            old={task['id']:task for task in before['tasks']}
            for task in after['tasks']:
                prior=old.get(task['id'])
                if prior and prior.get('name')==task.get('name'):
                    cpu.append({'task':task['name'],'runtime_fraction_of_wall':((task['ticks']-prior['ticks'])&0xffffffff)/span})
    result={'status':'fail' if errors else ('inconclusive' if missing else 'pass'),'errors':errors,'missing':missing,'cpu_tasks':cpu,
            'scope':'Isolated audio/speech/FFT only; no combined camera/UI/network or physical-channel acceptance.'}
    if not errors and not missing:
        result.update(sample_rate_observed_hz=2880000/(total/1e6),
                      read_interval_us=distribution(intervals),consumer_compute_us=distribution(compute),
                      read_complete_to_ready_us=distribution(ready_delays),
                      fft_interval_us=distribution([b-a for a,b in zip(fft_times,fft_times[1:])]),
                      memory_min={key:min(s[key] for s in memory) for key in memory[0] if key!='block_index'})
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('metadata',type=Path)
    args=parser.parse_args();meta,data=load_verified(args.metadata)
    result=compare_baseline(meta,data)
    path=args.metadata.with_name(args.metadata.stem+'-assessment.json')
    with path.open('x') as output:json.dump(result,output,indent=2);output.write('\n')
    print(json.dumps(result,indent=2))
    if result['status']!='pass':raise SystemExit(1)


if __name__=='__main__':main()
