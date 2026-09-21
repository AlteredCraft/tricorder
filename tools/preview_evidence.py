"""Join owned preview copies to native camera rows and real panel submissions."""
import argparse
import json
from pathlib import Path
import struct

from tools.audio_baseline_evidence import distribution
from tools.camera_baseline_evidence import compare_camera
from tools.inspect_capture import load_verified

POLICY='every second camera row; three owned buffers; replace only pending preview; display holds its source between renders'


def assess_preview(meta,data,ui_meta,ui_data,camera_rows,camera_epoch):
    errors=[];missing=[]
    required=dict(format='preview_frames_i64le',columns=8,width=640,height=360,buffer_count=3,buffer_bytes=460800,
                  pending_end=0,busy_drops=0,copy_errors=0,policy=POLICY,
                  resize='nearest RGB565 top-left pixel of each 2x2 source block')
    for key,value in required.items():
        if key not in meta:missing.append(key)
        elif meta[key]!=value:errors.append(key+' mismatch')
    for key in ('rows','camera_frames','throttled_frames','produced','selected','pending_replaced','acquisition_start_us','duration_us'):
        if key not in meta:missing.append(key)
        elif type(meta[key]) is not int or meta[key]<0:errors.append('Invalid '+key)
    for key,value in dict(format='preview_submissions_i64le',columns=11,observer_overflow=0).items():
        if key not in ui_meta:missing.append('ui '+key)
        elif ui_meta[key]!=value:errors.append('ui '+key+' mismatch')
    for key in ('rows','renders','acquisition_start_us','duration_us'):
        if key not in ui_meta:missing.append('ui '+key)
        elif type(ui_meta[key]) is not int or ui_meta[key]<=0:errors.append('Invalid ui '+key)
    base=dict(status='fail',errors=errors,missing=missing,animated_ui_acceptance=False,
              scope='Camera/JPEG plus nominal half-rate preview; no 30 fps animated-UI, physical-input or full combined acceptance.')
    if not data or len(data)%64 or not ui_data or len(ui_data)%88:
        errors.append('Incomplete preview/frame submission extent');return base
    if missing:
        base['status']='fail' if errors else 'inconclusive'
        return base
    rows=list(struct.iter_unpack('<8q',data));ui=list(struct.iter_unpack('<11q',ui_data))
    if meta.get('rows')!=len(rows) or ui_meta.get('rows')!=len(ui):errors.append('Row count mismatch')
    if meta.get('camera_frames')!=len(camera_rows) or len(rows)!=len(camera_rows)//2:
        errors.append('Every-second-camera-frame policy not accounted')
    if meta.get('throttled_frames')!=len(camera_rows)-len(rows):errors.append('Unaccounted throttled frames')
    if meta.get('acquisition_start_us')!=camera_epoch or ui_meta.get('acquisition_start_us')!=camera_epoch:
        errors.append('Camera/preview epoch mismatch')
    duration=meta.get('duration_us',0)
    if type(duration) is not int or not 60000000<=duration<=62000000 or ui_meta.get('duration_us')!=duration:
        errors.append('Incomplete or inconsistent preview window')
    selected={}
    for i,r in enumerate(rows):
        index,sequence,completed,dequeued,copy_start,copy_end,chosen,result=r
        camera=camera_rows[2*i+1] if 2*i+1<len(camera_rows) else None
        if index!=i+1 or not camera or (sequence,completed,dequeued)!=camera[:3]:
            errors.append('Preview source does not join its camera row');break
        if not 0<=completed<=dequeued<=copy_start<=copy_end or result!=0 or chosen<0 or (chosen and chosen<copy_end):
            errors.append('Preview copy/selection chronology or result invalid');break
        # The final source is intentionally copied after STREAMOFF. Other
        # camera buffers must not be requeued while their pixels are read.
        if i<len(rows)-1 and copy_end>camera[3]:
            errors.append('Preview read outlived native camera-buffer ownership');break
        if chosen:selected[index]=r
    if meta.get('produced')!=len(rows) or meta.get('selected')!=len(selected):errors.append('Unaccounted production/selection')
    if meta.get('pending_replaced')!=len(rows)-len(selected):errors.append('Unaccounted pending replacement')
    groups=[];previous=None
    for r in ui:
        render,generation,changed,submitted,returned,x1,y1,x2,y2,result,last=r
        frame=selected.get(generation)
        if (not frame or changed!=frame[6] or not changed<=submitted<=returned<=duration
                or x1<0 or y1<0 or x2<=x1 or y2<=y1 or result or last not in (0,1)):
            errors.append('Panel submission does not join a selected preview');break
        if previous and (submitted<previous[4] or generation<previous[1]):errors.append('Unordered panel submissions');break
        if not groups or render!=groups[-1][0][0]:
            if render!=len(groups)+1:errors.append('Missing render identity');break
            groups.append([])
        elif generation!=groups[-1][0][1] or changed!=groups[-1][0][2]:
            errors.append('Preview changed within one render');break
        groups[-1].append(r);previous=r
    if ui_meta.get('renders')!=len(groups):errors.append('Unaccounted render count')
    if any(any(r[-1] for r in g[:-1]) or g[-1][-1]!=1 for g in groups):errors.append('Incomplete/multiple final flushes')
    displayed=[]
    for group in groups:
        r=group[-1]
        if not displayed or r[1]!=displayed[-1][1]:displayed.append(r)
    if not displayed or displayed[-1][1]!=len(rows):errors.append('Final preview never submitted')
    gaps=[b[3]-a[3] for a,b in zip(displayed,displayed[1:])]
    ages=[r[3]-selected[r[1]][2] for r in displayed]
    if len(gaps)<2 or max(gaps)>200000:errors.append('Preview stalled beyond 200 ms')
    if ages and max(ages)>200000:errors.append('Displayed preview older than 200 ms')
    if displayed and (displayed[0][3]>200000 or duration-displayed[-1][3]>200000):
        errors.append('Preview start/end stall')
    base['status']='fail' if errors else ('inconclusive' if missing else 'pass')
    if not errors and not missing:
        base.update(produced=len(rows),selected=len(selected),pending_replaced=meta['pending_replaced'],
                    displayed_previews=len(displayed),selected_but_not_rendered=len(selected)-len(displayed),
                    repeated_renders=len(groups)-len(displayed),
                    submitted_fps=(len(displayed)-1)*1e6/(displayed[-1][3]-displayed[0][3]),
                    preview_interval_us=distribution(gaps),source_age_us=distribution(ages),
                    copy_us=distribution([r[5]-r[4] for r in rows]))
    return base


def verify_preview_witness(meta,data,raw_meta,raw):
    width,height=meta.get('width'),meta.get('height')
    if (meta.get('format')!='rgb565le' or raw_meta.get('format')!='rgb565le'
            or type(width) is not int or type(height) is not int or min(width,height)<=0
            or raw_meta.get('width')!=width*2 or raw_meta.get('height')!=height*2
            or len(data)!=width*height*2 or len(raw)!=width*height*8
            or not meta.get('source_sequence') or meta['source_sequence']!=raw_meta.get('completion_sequence')):
        raise ValueError('Preview witness layout/source mismatch')
    expected=bytearray(len(data))
    for y in range(height):
        line=raw[y*2*width*4:(y*2+1)*width*4]
        start=y*width*2
        expected[start:start+width*2:2]=line[0::4]
        expected[start+1:start+width*2:2]=line[1::4]
    if data!=expected:raise ValueError('Preview pixels differ from independently sampled native source')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('run',type=Path)
    args=parser.parse_args();run=args.run
    paths=list((run/'captures').glob('*-preview-frames.json'))
    if len(paths)!=1:raise ValueError('Expected one owned-preview trace')
    meta,data=load_verified(paths[0]);boot=meta['boot_id'];capture=run/'captures'
    ui_meta,ui_data=load_verified(capture/f'{boot}-preview-submissions.json')
    camera_meta,camera_data=load_verified(capture/f'{boot}-camera-baseline.json')
    camera_rows=list(struct.iter_unpack('<5Q',camera_data))
    result=assess_preview(meta,data,ui_meta,ui_data,camera_rows,camera_meta['acquisition_start_us'])
    result['camera_assessment']=compare_camera(camera_meta,camera_data)
    if result['camera_assessment']['status']!='pass':
        result['errors'].append('Independent native camera assessment did not pass');result['status']='fail'
    if json.loads((run/'summary.json').read_text())['status']!='pass':
        result['errors'].append('Final serial summary did not pass');result['status']='fail'
    try:
        preview,pixels=load_verified(capture/f'{boot}-preview-last.json')
        raw_meta,raw=load_verified(capture/f'{boot}-camera.json')
        if preview.get('boot_id')!=boot or raw_meta.get('boot_id')!=boot:raise ValueError('Witness boot mismatch')
        if preview.get('source_sequence')!=camera_rows[-1][0]:raise ValueError('Final preview is not the final camera source')
        verify_preview_witness(preview,pixels,raw_meta,raw)
        result['raw_witness_match']=True
    except (OSError,ValueError,KeyError) as error:
        result['errors'].append(str(error));result['status']='fail'
    with (run/'preview-assessment.json').open('x') as output:json.dump(result,output,indent=2)
    print(json.dumps(result,indent=2))
    if result['status']!='pass':raise SystemExit(1)


if __name__=='__main__':main()
