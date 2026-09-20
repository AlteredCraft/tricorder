"""Assess animated state-to-panel submissions, never physical presentation latency."""
import argparse
import json
from pathlib import Path
import struct
from tools.audio_baseline_evidence import distribution
from tools.inspect_capture import load_verified
from tools.workload_evidence import assess_cpu


def compare_ui(meta,data):
    errors=[];missing=[]
    expected={'format':'ui_baseline_i64le','columns':11,'animation_period_ms':33,'refresh_period_ms':20,'missed_animation_deadlines':0,'observer_overflow':0,
              'policy':'latest animation state per render; coalesced generations counted by host'}
    for key,value in expected.items():
        if key not in meta:missing.append(key)
        elif meta[key]!=value:errors.append(key+' mismatch')
    for key in ('rows','generations','renders','submissions','duration_us'):
        if key not in meta:missing.append(key)
        elif type(meta[key]) is not int or meta[key]<=0:errors.append('Invalid '+key)
    if not data or len(data)%88:return {'status':'fail','errors':errors+['Incomplete submission rows'],'missing':missing}
    rows=list(struct.iter_unpack('<11q',data))
    if any(key in meta and meta[key]!=len(rows) for key in ('rows','submissions')):errors.append('Unaccounted panel submissions')
    groups=[];previous=None
    for row in rows:
        render,generation,changed,submitted,returned,x1,y1,x2,y2,result,last=row
        if (render<=0 or generation<=0 or not 0<=changed<=submitted<=returned or x1<0 or y1<0
                or x2<=x1 or y2<=y1 or result!=0 or last not in (0,1)):
            errors.append('Invalid submission result/identity/timing/area');break
        if previous and (submitted<previous[4] or generation<previous[1]):errors.append('Unordered submissions');break
        if not groups or render!=groups[-1][0][0]:
            if render!=len(groups)+1:errors.append('Missing render identity');break
            groups.append([])
        elif generation!=groups[-1][0][1] or changed!=groups[-1][0][2]:
            errors.append('Animation changed within one render');break
        groups[-1].append(row);previous=row
    if 'renders' in meta and meta['renders']!=len(groups):errors.append('Unaccounted renders')
    if any(any(r[-1] for r in group[:-1]) or group[-1][-1]!=1 for group in groups):errors.append('Incomplete/multiple last flushes')
    frames=[group[-1] for group in groups]
    animated=[]
    for frame in frames:
        if not animated or frame[1]!=animated[-1][1]:animated.append(frame)
    duration=meta.get('duration_us')
    if duration is not None and (not 60000000<=duration<=62000000 or duration<rows[-1][4]):errors.append('Incomplete/invalid 60-second window')
    if 'generations' in meta and frames and meta['generations']!=frames[-1][1]:errors.append('Unsubmitted final animation state')
    intervals=[b[3]-a[3] for a,b in zip(animated,animated[1:])]
    if len(intervals)<2:errors.append('Insufficient distinct animation submissions')
    elif distribution(intervals)['p95']>50000 or max(intervals)>200000:errors.append('Animation frame-interval target missed')
    rate=(len(animated)-1)*1e6/(animated[-1][3]-animated[0][3]) if len(animated)>1 and animated[-1][3]>animated[0][3] else 0
    if rate<30:errors.append('Animation submissions below 30 fps target')
    if animated and duration is not None and (animated[0][3]>200000 or duration-animated[-1][3]>200000):
        errors.append('Unobserved start/end animation stall')
    cpu,cpu_errors,cpu_missing=assess_cpu(meta);errors.extend(cpu_errors);missing.extend(cpu_missing)
    samples=meta.get('memory_samples',[])
    keys=('free_internal','free_psram','largest_psram','stack_margin_bytes','free_task_sram','largest_task_sram')
    if len(samples)!=60:missing.append('memory sampling cadence')
    else:
        for index,sample in enumerate(samples,1):
            if sample.get('second')!=index:errors.append('Memory sample position mismatch')
            for key in keys:
                if key not in sample:missing.append(key)
                elif type(sample[key]) is not int or sample[key]<=0:errors.append('Invalid memory '+key)
    result={'status':'fail' if errors else ('inconclusive' if missing else 'pass'),'errors':errors,'missing':missing,'cpu_tasks':cpu,
            'scope':'Isolated animated UI software panel submission; no physical presentation, touch latency or combined-load claim.'}
    if not errors and not missing:
        result.update(frames=len(frames),animated_frames=len(animated),repeated_states=len(frames)-len(animated),
                      coalesced_generations=meta['generations']-len(animated),
                      submitted_fps=rate,
                      frame_interval_us=distribution(intervals),
                      change_to_submit_us=distribution([r[3]-r[2] for r in animated]),
                      panel_call_us=distribution([r[4]-r[3] for r in rows]),
                      memory_min={key:min(s[key] for s in samples) for key in keys})
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('metadata',type=Path)
    args=parser.parse_args();meta,data=load_verified(args.metadata);result=compare_ui(meta,data)
    with args.metadata.with_name(args.metadata.stem+'-assessment.json').open('x') as output:
        json.dump(result,output,indent=2);output.write('\n')
    print(json.dumps(result,indent=2))
    if result['status']!='pass':raise SystemExit(1)

if __name__=='__main__':main()
