"""Verify fresh-frame JPEG provenance and bounded encode timing before decoding images."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
from tools.inspect_capture import load_verified
from tools.audio_baseline_evidence import distribution
from tools.camera_baseline_evidence import compare_camera


def assess_records(meta,camera):
    errors=[];missing=[]
    expected={'quality':75,'subsampling':'YUV420','source_format':'rgb565le','attempts':30,'busy_drops':0,'pool_overflows':0}
    for key,value in expected.items():
        if key not in meta:missing.append(key)
        elif meta[key]!=value:errors.append(key+' mismatch')
    for key in ('width','height','source_bytes','output_capacity','pool_capacity','epoch_start_us'):
        if key not in meta:missing.append(key)
        elif type(meta[key]) is not int or meta[key]<=0:errors.append('Invalid '+key)
    if all(key in meta for key in ('width','height','source_bytes')) and meta['source_bytes']!=meta['width']*meta['height']*2:
        errors.append('Source extent mismatch')
    records=meta.get('records',[])
    if len(records)!=30:errors.append('Expected 30 fresh JPEG results')
    used=0;prior=0;durations=[];delays=[];source_hashes=[];source_copies=[]
    for index,r in enumerate(records,1):
        required=('index','source_sequence','source_completed_us','dequeued_us','copied_us','encode_start_us','encode_end_us',
                  'source_sha256','copy_sha256','after_sha256','jpeg_bytes','result',
                  'source_hash_start_us','source_hash_end_us','copy_start_us')
        if any(key not in r for key in required):missing.append('JPEG record fields');continue
        if r['index']!=index or r['source_sequence']<=prior or r['result']!=0:errors.append('Invalid result or source identity')
        prior=r['source_sequence']
        if camera.get(r['source_sequence'])!=(r['source_completed_us'],r['dequeued_us']):errors.append('Source camera join failed')
        times=[r[key] for key in ('source_completed_us','dequeued_us','copied_us','encode_start_us','encode_end_us')]
        if times!=sorted(times) or times[0]<index*2000000-100000 or times[1]<index*2000000 or times[-1]>(index+1)*2000000:
            errors.append('Stale source or encode deadline missed')
        source_times=[r[key] for key in ('dequeued_us','source_hash_start_us','source_hash_end_us','copy_start_us','copied_us')]
        if source_times!=sorted(source_times):errors.append('Invalid source hash/copy timing')
        source_hashes.append(r['source_hash_end_us']-r['source_hash_start_us'])
        source_copies.append(r['copied_us']-r['copy_start_us'])
        hashes=[r[key] for key in ('source_sha256','copy_sha256','after_sha256')]
        if len(set(hashes))!=1 or any(not isinstance(h,str) or len(h)!=64 or any(c not in '0123456789abcdef' for c in h) for h in hashes):
            errors.append('Owned source hash/mutation mismatch')
        if r['jpeg_bytes']<=0 or ('output_capacity' in meta and r['jpeg_bytes']>meta['output_capacity']):errors.append('Output extent mismatch')
        used+=r['jpeg_bytes'];durations.append(times[-1]-times[-2]);delays.append(times[-1]-times[0])
    if 'pool_capacity' in meta and used>meta['pool_capacity']:errors.append('Retention pool overflow')
    result={'status':'fail' if errors else ('inconclusive' if missing else 'pass'),'errors':errors,'missing':missing,
            'scope':'Camera plus owned-frame JPEG encoder; no network, preview, audio or full combined-load acceptance.'}
    if not errors and not missing:result.update(encode_worker_us=distribution(durations),source_to_encoded_us=distribution(delays),jpeg_bytes=used,
                                               source_hash_us=distribution(source_hashes),source_copy_us=distribution(source_copies))
    return result


def assess_run(meta,camera_meta,camera_data,summary):
    camera={r[0]:(r[1],r[2]) for r in struct.iter_unpack('<5Q',camera_data)}
    result=assess_records(meta,camera)
    result['camera_assessment']=compare_camera(camera_meta,camera_data)
    if result['camera_assessment']['status']!='pass':
        result['errors'].append('Independent camera baseline did not pass');result['status']='fail'
    if summary['status']!='pass':
        result['errors'].append('Final run did not pass');result['status']='fail'
    return result


def verify_image_record(image,data,record,baseline):
    expected={key:baseline[key] for key in ('boot_id','width','height','quality','subsampling')}
    expected.update(format='jpeg',source_sequence=record['source_sequence'],
                    source_completed_device_us=baseline['epoch_start_us']+record['source_completed_us'],
                    source_sha256=record['source_sha256'])
    if len(data)!=record['jpeg_bytes'] or any(image.get(key)!=value for key,value in expected.items()):
        raise ValueError('JPEG provenance/settings/size mismatch')


def verify_witness(record,witness,data):
    if (witness.get('format')!='rgb565le' or witness.get('completion_sequence')!=record['source_sequence']
            or witness.get('sha256')!=record['source_sha256']
            or hashlib.sha256(data).hexdigest()!=record['source_sha256']):
        raise ValueError('Retained raw source witness mismatch')


def decode_jpeg(path,meta,output):
    _,data=load_verified(path)
    if not data.startswith(b'\xff\xd8') or not data.endswith(b'\xff\xd9'):raise ValueError('JPEG marker extent mismatch')
    probe=subprocess.run(['ffprobe','-v','error','-count_frames','-select_streams','v:0','-show_entries',
                          'stream=codec_name,width,height,nb_read_frames','-of','json',str(path.with_suffix('.bin'))],
                         check=True,capture_output=True,text=True)
    streams=json.loads(probe.stdout)['streams']
    if len(streams)!=1 or streams[0].get('codec_name')!='mjpeg' or streams[0].get('nb_read_frames')!='1':
        raise ValueError('Expected one decodable JPEG frame')
    if (streams[0]['width'],streams[0]['height'])!=(meta['width'],meta['height']):raise ValueError('Decoded dimensions mismatch')
    subprocess.run(['ffmpeg','-nostdin','-v','error','-xerror','-n','-i',str(path.with_suffix('.bin')),
                    '-frames:v','1',str(output)],check=True,capture_output=True)


def is_camera_witness(meta,boot_id):
    return (meta.get('format')=='rgb565le' and meta.get('boot_id')==boot_id
            and meta.get('capture_id')==boot_id+'-camera')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('run',type=Path)
    args=parser.parse_args();run=args.run
    events=[json.loads(l) for l in (run/'events.jsonl').read_text().splitlines()]
    summaries=[e for e in events if e.get('event')=='jpeg_baseline']
    if len(summaries)!=1:raise ValueError('Expected one JPEG baseline event')
    meta=summaries[0]
    camera_path=run/'captures'/f"{meta['boot_id']}-camera-baseline.json"
    camera_meta,camera_data=load_verified(camera_path)
    if camera_meta['acquisition_start_us']!=meta['epoch_start_us']:raise ValueError('Camera epoch mismatch')
    original=json.loads((run/'summary.json').read_text())
    result=assess_run(meta,camera_meta,camera_data,original);result['decoded']=[]
    for record in meta.get('records',[]):
        capture_id=f"{meta['boot_id']}-jpeg-{record['index']}";path=run/'captures'/f'{capture_id}.json'
        try:
            image_meta,data=load_verified(path)
            verify_image_record(image_meta,data,record,meta)
            target=path.with_suffix('.png');decode_jpeg(path,meta,target);result['decoded'].append(str(target))
        except (ValueError,KeyError,OSError,subprocess.CalledProcessError) as error:
            result['errors'].append(capture_id+': '+str(error));result['status']='fail'
    witnesses=[]
    for path in (run/'captures').glob('*.json'):
        candidate=json.loads(path.read_text())
        if is_camera_witness(candidate,meta['boot_id']):
            witnesses.append(path)
    try:
        if len(witnesses)!=1:raise ValueError('Expected one retained raw source witness')
        witness,data=load_verified(witnesses[0])
        records=[r for r in meta['records'] if r['source_sequence']==witness.get('completion_sequence')]
        if len(records)!=1:raise ValueError('Raw source witness does not join a JPEG record')
        verify_witness(records[0],witness,data)
        result['raw_source_witness']=str(witnesses[0])
    except (ValueError,KeyError,OSError) as error:
        result['errors'].append(str(error));result['status']='fail'
    with (run/'jpeg-assessment.json').open('x') as output:json.dump(result,output,indent=2)
    print(json.dumps(result,indent=2))
    if result['status']!='pass':raise SystemExit(1)

if __name__=='__main__':main()
