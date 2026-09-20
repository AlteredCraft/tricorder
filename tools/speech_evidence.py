"""Independent speech-conditioning reference and raw/source-range checks."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct

from tools.audio_reference import pcm_fixtures
from tools.inspect_capture import load_verified


def speech_reference(samples, enabled):
    if not enabled: return list(samples)
    alpha=math.exp(-2*math.pi*80/48000)
    highpass=[];previous_x=previous_y=0
    for sample in samples:
        value=sample-previous_x+alpha*previous_y
        highpass.append(value);previous_x=sample;previous_y=value
    coefficients=[]
    for n in range(63):
        x=n-31
        sinc=2*6500/48000 if x==0 else math.sin(2*math.pi*6500*x/48000)/(math.pi*x)
        coefficients.append(sinc*(.42-.5*math.cos(2*math.pi*n/62)+.08*math.cos(4*math.pi*n/62)))
    total=math.fsum(coefficients)
    coefficients=[c/total for c in coefficients]
    output=[]
    for n in range(2,len(samples),3):
        value=math.fsum(highpass[n-k]*c for k,c in enumerate(coefficients) if n>=k)
        rounded=math.floor(value+.5) if value>=0 else math.ceil(value-.5)
        output.append(max(-32768,min(32767,rounded)))
    return output


def compare_pair(raw_meta,raw,speech_meta,speech):
    errors=[]
    name=raw_meta.get('fixture_id');enabled=raw_meta.get('speech_enabled')
    samples=pcm_fixtures().get(name)
    if samples is None or type(enabled) is not bool:
        return {'status':'fail','errors':['Unknown fixture or processing mode']}
    expected_raw=struct.pack('<'+'h'*len(samples),*samples)
    digest=hashlib.sha256(expected_raw).hexdigest()
    if raw!=expected_raw:errors.append('Raw bytes differ from injected fixture')
    raw_expected={'input_sha256_before':digest,'input_sha256_after':digest,'channels':1,
                  'format':'pcm_s16le','sample_rate_hz':48000,'frames':len(samples),'role':'measurement_replay'}
    for key,value in raw_expected.items():
        if raw_meta.get(key)!=value:errors.append(f'Raw {key} mismatch')
    offset=0
    for block in raw_meta.get('ingress_blocks',[]):
        frames=block.get('frames')
        if type(frames) is not int or frames<=0 or block.get('source_start_frame')!=offset or offset+frames>len(samples):
            errors.append('Invalid ingress sample range');break
        if hashlib.sha256(raw[offset*2:(offset+frames)*2]).hexdigest()!=block.get('sha256'):
            errors.append('Ingress block hash mismatch')
        offset+=frames
    if offset!=len(samples):errors.append('Missing ingress sample ranges')
    output=speech_reference(samples,enabled)
    expected={'source_capture_id':raw_meta.get('capture_id'),'boot_id':raw_meta.get('boot_id'),
              'fixture_id':name,'repetition':raw_meta.get('repetition'),'speech_enabled':enabled,
              'role':'speech_replay','format':'pcm_s16le','channels':1,'frames':len(output),
              'sample_rate_hz':16000 if enabled else 48000,'source_start_frame':0,'source_frames':len(samples),
              'input_clipped':sum(x in (-32768,32767) for x in samples),'output_clipped':0,
              'processing':'dc80-fir63-fc6500-decimate3-v1' if enabled else 'selected-slot-copy-v1'}
    for key,value in expected.items():
        if value is None or speech_meta.get(key)!=value:errors.append(f'Speech {key} mismatch')
    if type(speech_meta.get('compute_us')) is not int or speech_meta['compute_us']<0:
        errors.append('Invalid compute duration')
    maximum_error=None
    if len(speech)!=len(output)*2:errors.append('Wrong speech byte count')
    else:
        actual=struct.unpack('<'+'h'*len(output),speech)
        maximum_error=max(abs(a-b) for a,b in zip(actual,output))
        if maximum_error>(2 if enabled else 0):errors.append('Speech differs from independent reference')
    return {'status':'fail' if errors else 'pass','fixture_id':name,'speech_enabled':enabled,
            'repetition':raw_meta.get('repetition'),'errors':errors,'max_sample_error_counts':maximum_error,
            'compute_us':speech_meta.get('compute_us')}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run',type=Path)
    args=parser.parse_args()
    captures={}
    for path in (args.run/'captures').glob('*.json'):
        metadata=json.loads(path.read_text())
        if metadata.get('role') in ('measurement_replay','speech_replay'):
            metadata,data=load_verified(path)
            captures[metadata['capture_id']]=(metadata,data)
    expected={(name,enabled,repetition) for name in pcm_fixtures() for enabled in (False,True) for repetition in (1,2,3)}
    seen=set();boots=set();used_raw=set();errors=[];results=[]
    for speech_meta,speech in captures.values():
        if speech_meta['role']!='speech_replay':continue
        key=(speech_meta.get('fixture_id'),speech_meta.get('speech_enabled'),speech_meta.get('repetition'))
        source_id=speech_meta.get('source_capture_id')
        if key not in expected or key in seen or source_id not in captures or source_id in used_raw:
            errors.append('Missing source, duplicate or unexpected replay');continue
        seen.add(key);boots.add(speech_meta['boot_id']);used_raw.add(source_id)
        raw_meta,raw=captures[source_id]
        results.append(compare_pair(raw_meta,raw,speech_meta,speech))
    if seen!=expected or len(captures)!=48:errors.append('Expected exactly 24 raw/speech replay pairs')
    if len(boots)!=1:errors.append('Expected one device boot')
    original=json.loads((args.run/'summary.json').read_text())
    if original.get('capture_errors') or original.get('integrity_errors') or original.get('incomplete_captures'):
        errors.append('Run/capture integrity failed')
    result={'status':'fail' if errors or any(x['status']!='pass' for x in results) else 'pass',
            'errors':errors,'replays':results,
            'scope':'Synthetic synchronous consumers only; no live continuity, asynchronous lifetime, SD or acoustic acceptance.'}
    with (args.run/'speech-replay.json').open('x') as output:
        json.dump(result,output,indent=2);output.write('\n')
    print(json.dumps(result,indent=2))
    if result['status']!='pass':raise SystemExit(1)


if __name__=='__main__':main()
