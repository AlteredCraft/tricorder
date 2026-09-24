"""Independently recompute a saved A/B exchange; no provider/reducer imports.

This assesses recorded bytes and protocol joins only. It cannot establish the
physical fixture, responsiveness, usefulness or G-0002 acceptance on its own.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct


QUESTION_TYPES=('question_start','question_end','transcript','question_confirm')


def spoken_questions(root,rows,traffic):
    """Check the spoken-ask exchange (before Record A only) and return the A/B traffic."""
    def check(ok,reason):
        if not ok:raise ValueError(reason)
    first=next((i for i,m in enumerate(traffic) if m['type']=='capture_start'),len(traffic))
    check(all(m['type'] not in QUESTION_TYPES for m in traffic[first:]),'question traffic after Record A')
    analyses={r['question_id']:r for r in rows if r.get('type')=='question_analysis'}
    answers=[r for r in rows if r.get('type')=='operator_question']
    questions=[];heard={};operator_question=None
    for m in traffic[:first]:
        if m['type']=='question_start':
            meta=m['metadata'];key=meta['question_id']
            check(isinstance(key,str) and '/' not in key and '\\' not in key,'unsafe question identity')
            raw=(root/'questions'/f'{key}.bin').read_bytes()
            check(len(raw)==meta['size_bytes']==meta['frames']*2 and meta['sample_rate_hz']==16000
                  and meta['channels']==1 and hashlib.sha256(raw).hexdigest()==meta['sha256'],'question audio mismatch')
            questions.append(dict(question_id=key,duration_s=meta['frames']/16000,stopped_by=meta['stopped_by']))
        elif m['type']=='question_end':
            check(questions and m['question_id']==questions[-1]['question_id'],'question end identity')
        elif m['type']=='transcript':
            q=questions[-1] if questions else {}
            check(m['question_id']==q.get('question_id'),'transcript identity')
            record=analyses.get(m['question_id'],{})
            level=record.get('speech_to_noise_db')
            check(record.get('status')==m['status'] and record.get('text')==m['text'],'transcript not joined to its analysis')
            check(m['speech_to_noise_db']==(None if level is None else round(level,1)),'speech-to-noise level mismatch')
            q.update(status=m['status'],text=m['text'],speech_to_noise_db=m['speech_to_noise_db'],accepted=None)
            if m['status']=='heard':heard[m['question_id']]=m['text']
        elif m['type']=='question_confirm':
            key=m['question_id']
            check(key in heard,'confirmation without a heard transcript')
            answer=next((r for r in answers if r['question_id']==key),None)
            check(answer is not None and answer['accepted'] is m['accepted'] and answer['text']==heard.pop(key),'confirmation record mismatch')
            questions[-1]['accepted']=m['accepted']
            if m['accepted']:operator_question=answer['text']
    return [m for m in traffic if m['type'] not in QUESTION_TYPES],questions,operator_question


def assess_run(root):
    root=Path(root)
    result=dict(status='fail',scope='saved A/B bytes and transcript joins only; no physical/live acceptance',errors=[])
    def check(ok,reason):
        if not ok:raise ValueError(reason)
    try:
        manifest=json.loads((root/'manifest.json').read_text())
        fixture=manifest['fixture'];boot=manifest['boot_id'];session=manifest['session_id']
        rows=[json.loads(line)['message'] for line in (root/'transcript.jsonl').read_text().splitlines()]
        traffic=[r['payload'] for r in rows if 'payload' in r]
        replay=manifest.get('replay',False)
        check(type(replay) is bool and traffic and traffic[0].get('replay',False) is replay,'replay label mismatch')
        result['replay']=replay
        if replay:result['scope']='SD transport replay; no new sensor acquisition or physical/live acceptance'
        check(all(m.get('version')==1 and m.get('boot_id')==boot and m.get('session_id')==session for m in traffic),'wire identity mismatch')
        traffic,questions,operator_question=spoken_questions(root,rows,traffic)
        result.update(questions=questions,operator_question=operator_question)
        expected=['hello','ready']+['capture_start','capture_ack','capture_end','capture_ack','turn','guidance','ack','acknowledged']+['capture_start','capture_ack','capture_end','capture_ack','turn','comparison','ack','acknowledged']
        check([m['type'] for m in traffic]==expected,'incomplete/out-of-order exchange')
        captures=[];proofs=[]
        for index,base in enumerate([2,10]):
            messages=traffic[base:base+8]
            key=messages[0]['metadata']['capture_id']
            check(isinstance(key,str) and '/' not in key and '\\' not in key,'unsafe capture identity')
            meta=json.loads((root/'captures'/f'{key}.json').read_text())
            raw=(root/'captures'/f'{key}.bin').read_bytes()
            check(meta['status']=='complete' and meta['boot_id']==boot and meta['session_id']==session and meta['capture_id']==key,'saved identity/completion')
            check(len(raw)==meta['size_bytes']==fixture['frames']*8,'raw extent mismatch')
            check(hashlib.sha256(raw).hexdigest()==meta['sha256'],'raw hash mismatch')
            for setting in ('sample_rate_hz','frames','channels','gain_db','source_slot','physical_slot'):
                check(meta[setting]==fixture[setting],f'changed setting: {setting}')
            check(meta['format']=='pcm_s16le' and meta['driver_epoch_integrity'] is True and meta['speaker_active'] is False,'measurement window invalid')
            check(meta['acquisition_end_us']>meta['acquisition_start_us'],'invalid acquisition window')
            if captures:check(meta['acquisition_start_us']>=captures[0]['end_us'],'overlapping captures')
            samples=[value[0] for value in struct.iter_unpack('<h',raw)]
            selected=samples[fixture['source_slot']::4]
            rms=math.sqrt(math.fsum(x*x for x in selected)/len(selected))
            values=dict(frames=len(selected),rms_counts=rms,peak_counts=max(abs(x) for x in selected),
                        clipped_samples=sum(x in (-32768,32767) for x in selected),
                        rms_dbfs=20*math.log10(rms/32768) if rms else None)
            captures.append(dict(capture_id=key,sha256=meta['sha256'],end_us=meta['acquisition_end_us'],measurement=values))
            check(messages[1]['capture_id']==messages[2]['capture_id']==messages[3]['capture_id']==key,'upload ACK identity')
            check(messages[1]['stage']=='start' and messages[3]['stage']=='complete','upload ACK stage')
            check(messages[2]['sha256']==messages[3]['sha256']==meta['sha256'],'upload ACK digest')
            turn,reply,ack,done=messages[4:]
            check(turn['capture_ids']==reply['capture_ids']==[c['capture_id'] for c in captures],'evidence join mismatch')
            check(turn['request_id']==reply['request_id']==ack['request_id']==done['request_id'],'turn ACK mismatch')
            check(turn['deadline_ms']==reply['deadline_ms'] and turn['device_ms']<turn['deadline_ms'],'deadline mismatch')
            check(done['state']==('adjust' if index==0 else 'complete'),'final acknowledgement missing')
            check(len(reply['measurements'])==len(captures),'measurement count')
            for supplied,computed in zip(reply['measurements'],[c['measurement'] for c in captures]):
                check(set(supplied)==set(computed),'measurement fields')
                for name,value in computed.items():
                    actual=supplied[name]
                    check(actual is None if value is None else type(actual) in (int,float) and math.isfinite(actual) and math.isclose(actual,value,rel_tol=1e-10,abs_tol=1e-10),f'unbacked {name}')
            if index==0:check(reply['comparison'] is None,'premature comparison')
            else:check(isinstance(turn.get('adjustment'),str) and turn['adjustment'].strip(),'adjustment missing')
            has_proof='ingress_blocks' in meta
            if has_proof:
                offset=0;previous=meta['acquisition_start_us']
                for block in meta['ingress_blocks']:
                    n=block['frames'];check(n>0 and block['source_start_frame']==offset,'ingress ordering')
                    check(previous<=block['read_end_us']<=meta['acquisition_end_us'],'ingress timestamp')
                    previous=block['read_end_us']
                    check(hashlib.sha256(raw[offset*8:(offset+n)*8]).hexdigest()==block['sha256'],'ingress hash')
                    offset+=n
                check(offset==fixture['frames'],'ingress extent')
                before,after=meta['ingress_before'],meta['ingress_after']
                warmup=meta.get('warmup_frames',0)
                check(type(warmup) is int and warmup in (0,24000),'invalid settling prefix')
                if warmup:check(0<=meta['epoch_start_us']<meta['acquisition_start_us'],'settling window')
                extent=len(raw)+warmup*8
                check(after['read_bytes']-before['read_bytes']==extent and after['dma_bytes']-before['dma_bytes']>=extent,'driver extent')
                check(all(before[k]==after[k] for k in ('overflows','overwritten_bytes','short_reads','read_errors')),'driver loss/error')
            proofs.append(has_proof)
        a,b=(c['measurement'] for c in captures)
        valid=a['rms_counts']>0 and b['rms_counts']>0 and not(a['clipped_samples'] or b['clipped_samples'])
        delta=20*math.log10(b['rms_counts']/a['rms_counts']) if valid else None
        comparison=traffic[-3]['comparison']
        check(comparison['status']==('measured' if valid else 'inconclusive'),'comparison status')
        check(comparison['rms_delta_db'] is None if delta is None else math.isclose(comparison['rms_delta_db'],delta,rel_tol=1e-10,abs_tol=1e-10),'comparison ratio')
        check(captures[0]['capture_id']!=captures[1]['capture_id'],'duplicate A/B')
        result.update(status='pass',boot_id=boot,session_id=session,captures=captures,
                      driver_proofs_present=all(proofs),rms_delta_db=delta,comparison_status=comparison['status'])
    except (OSError,ValueError,KeyError,TypeError,IndexError,struct.error) as error:
        result['errors'].append(str(error))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('run',type=Path)
    args=parser.parse_args();result=assess_run(args.run);print(json.dumps(result,indent=2,allow_nan=False))
    if result['status']!='pass':raise SystemExit(1)

if __name__=='__main__':main()
