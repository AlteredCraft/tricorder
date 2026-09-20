"""Assess camera completion identity, timing and observed backup-buffer starvation."""
import argparse
import json
from pathlib import Path
import struct
from tools.audio_baseline_evidence import distribution
from tools.inspect_capture import load_verified


def compare_camera(meta,data):
    errors=[];missing=[]
    required=('rows','columns','width','height','frame_bytes','duration_us','completed_before','completed_after',
              'missing_buffers','untracked_buffers','completed_bytes','discarded_completed_at_stop',
              'cpu_before','cpu_after','memory_samples')
    missing=[key for key in required if key not in meta]
    if meta.get('format')!='camera_baseline_u64le' or meta.get('columns')!=5:
        return {'status':'fail','errors':['Invalid timing format'],'missing':missing}
    count=meta.get('rows');size=meta.get('frame_bytes');duration=meta.get('duration_us')
    if type(count) is not int or count<2 or len(data)!=count*40:
        return {'status':'fail','errors':['Incomplete timing extent'],'missing':missing}
    rows=list(struct.iter_unpack('<5Q',data))
    if all(key in meta for key in ('width','height','frame_bytes')):
        if min(meta['width'],meta['height'])<=0 or size!=meta['width']*meta['height']*2:errors.append('RGB565 dimensions/size mismatch')
    previous_sequence=meta.get('completed_before');previous_done=None
    for sequence,done,dequeued,released,used in rows:
        if ((previous_sequence is not None and sequence!=previous_sequence+1)
                or (previous_done is not None and done<=previous_done) or dequeued<done or released<dequeued
                or (size is not None and used!=size)):
            errors.append('Frame identity/timing/size mismatch');break
        previous_sequence=sequence;previous_done=done
    if duration is not None and (type(duration) is not int or duration<60000000 or duration<rows[-1][3]):
        errors.append('Incomplete/invalid 60-second window')
    for key in ('missing_buffers','untracked_buffers'):
        if key in meta and meta[key]!=0:errors.append('Observed '+key)
    if all(key in meta for key in ('completed_before','completed_after','discarded_completed_at_stop','completed_bytes','frame_bytes')):
        tail=meta['discarded_completed_at_stop'];completed=meta['completed_after']-meta['completed_before']
        if type(tail) is not int or not 0<=tail<=2 or completed!=count+tail or meta['completed_bytes']!=completed*size:
            errors.append('Unaccounted camera completions/bytes')
    cpu=[];snapshots=[]
    for key in ('cpu_before','cpu_after'):
        snapshot=meta.get(key,{})
        tasks=snapshot.get('tasks',[])
        if type(snapshot.get('total_ticks')) is not int or not tasks:
            missing.append(key+' runtime evidence');continue
        if any(type(task.get('id')) is not int or not isinstance(task.get('name'),str)
               or type(task.get('ticks')) is not int or type(task.get('stack_margin_bytes')) is not int for task in tasks):
            missing.append(key+' task counters/stack');continue
        if len({t['id'] for t in tasks})!=len(tasks) or any(t['ticks']<0 or t['stack_margin_bytes']<=0 for t in tasks):
            errors.append('Invalid CPU task evidence');continue
        snapshots.append(snapshot)
    if len(snapshots)==2:
        before,after=snapshots;span=(after['total_ticks']-before['total_ticks']) & 0xffffffff
        old={t['id']:t for t in before['tasks']}
        if not span:errors.append('Invalid CPU runtime span')
        else:
            for task in after['tasks']:
                prior=old.get(task['id'])
                if not prior or prior['name']!=task['name']:
                    missing.append('CPU task lifetime '+task['name']);continue
                cpu.append({'task':task['name'],'runtime_fraction_of_wall':((task['ticks']-prior['ticks']) & 0xffffffff)/span,
                            'stack_margin_bytes':min(task['stack_margin_bytes'],prior['stack_margin_bytes'])})
    samples=meta.get('memory_samples')
    if samples is not None:
        if len(samples)!=count//30:missing.append('memory sampling cadence')
        for index,sample in enumerate(samples,1):
            if sample.get('frame_index')!=index*30 or any(type(sample.get(key)) is not int or sample[key]<=0 for key in
                    ('free_internal','free_psram','largest_psram','stack_margin_bytes')):
                errors.append('Invalid memory sample');break
            for key in ('free_task_sram','largest_task_sram'):
                if key not in sample:missing.append(key)
                elif type(sample[key]) is not int or sample[key]<=0:errors.append('Invalid '+key)
            if size and sample['largest_psram']<size:errors.append('Largest PSRAM block below frame allocation')
    rate=(count-1)*1e6/(rows[-1][1]-rows[0][1]) if rows[-1][1]>rows[0][1] else 0
    if rate<15:errors.append('Capture rate below 15 fps starting target')
    result={'status':'fail' if errors else ('inconclusive' if missing else 'pass'),'errors':errors,'missing':missing,
            'frames':count,'capture_fps':rate,'cpu_tasks':cpu,'scope':'Isolated native camera acquisition; no preview, JPEG/network or combined-load acceptance.'}
    if not errors and not missing:
        result.update(frame_interval_us=distribution([b[1]-a[1] for a,b in zip(rows,rows[1:])]),
                      completion_to_dequeue_us=distribution([row[2]-row[1] for row in rows]),
                      buffer_hold_us=distribution([row[3]-row[2] for row in rows]),
                      memory_min={key:min(sample[key] for sample in samples) for key in
                                  ('free_internal','free_psram','largest_psram','stack_margin_bytes','free_task_sram','largest_task_sram')})
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('metadata',type=Path)
    args=parser.parse_args();meta,data=load_verified(args.metadata);result=compare_camera(meta,data)
    with args.metadata.with_name(args.metadata.stem+'-assessment.json').open('x') as output:
        json.dump(result,output,indent=2);output.write('\n')
    print(json.dumps(result,indent=2))
    if result['status']!='pass':raise SystemExit(1)


if __name__=='__main__':main()
