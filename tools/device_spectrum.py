"""Compare a complete device spectrum with an independently computed PCM reference."""
import math
import struct
import argparse
import hashlib
import json
from pathlib import Path

from tools.audio_reference import pcm_fixtures
from tools.inspect_capture import load_verified


def compare_fixture(record, metadata, data):
    reference=record['reference']
    errors=[]
    expected={'fixture_id':record['fixture_id'],'format':'spectrum_f32le',
              'input_sha256_before':record['sha256'],'input_sha256_after':record['sha256'],
              'clipped_samples':record['clipped_samples']}
    expected.update({key:reference[key] for key in ('frames','sample_rate_hz','window','normalization','pcm_scale')})
    for key,value in expected.items():
        if metadata.get(key)!=value: errors.append(f'{key} mismatch')
    if type(metadata.get('compute_us')) is not int or metadata['compute_us']<0:
        errors.append('invalid compute duration')
    count=len(reference['amplitude_fs'])
    maximum_error=None
    if len(data)!=4*count:
        errors.append('incomplete or oversized spectrum')
    else:
        values=struct.unpack('<'+'f'*count,data)
        if not all(math.isfinite(value) and value>=0 for value in values):
            errors.append('invalid spectrum values')
        else:
            maximum_error=max(abs(actual-expected) for actual,expected in zip(values,reference['amplitude_fs']))
            if maximum_error>1e-5: errors.append('full-spectrum error exceeds 1e-5 FS')
    peak=metadata.get('peak_bin')
    expected_peak=reference['peak_bin']
    if expected_peak is None:
        if peak not in (None,-1): errors.append('spurious unique peak')
    elif type(peak) is not int or abs(peak-expected_peak)>1:
        errors.append('dominant frequency exceeds one-bin tolerance')
    amplitude=metadata.get('peak_amplitude_fs')
    if not isinstance(amplitude,(int,float)) or not math.isfinite(amplitude) or amplitude<0:
        errors.append('invalid peak amplitude')
    elif reference['peak_amplitude_fs']>=reference['amplitude_floor_fs']:
        if abs(amplitude-reference['peak_amplitude_fs'])>0.01*reference['peak_amplitude_fs']:
            errors.append('peak amplitude error exceeds 1 percent')
    elif amplitude>reference['amplitude_floor_fs']:
        errors.append('peak exceeds numerical floor')
    return {'fixture_id':record['fixture_id'],'status':'fail' if errors else 'pass',
            'errors':errors,'max_bin_error_fs':maximum_error,'compute_us':metadata.get('compute_us')}


def assess_fixture_set(records, captures):
    references={record['fixture_id']:record for record in records}
    expected={(name,repetition) for name in references for repetition in (1,2,3)}
    seen=set();boots=set();results=[];errors=[]
    for metadata,data in captures:
        name=metadata.get('fixture_id');repetition=metadata.get('repetition')
        key=(name,repetition)
        if key not in expected or key in seen:
            errors.append('Unexpected or duplicate fixture/repetition')
            continue
        seen.add(key);boots.add(metadata.get('boot_id'))
        result=compare_fixture(references[name],metadata,data)
        result['repetition']=repetition
        results.append(result)
    if seen!=expected: errors.append('Missing fixture repetitions')
    if len(boots)!=1 or None in boots: errors.append('Expected one explicit device boot')
    failed=errors or any(result['status']!='pass' for result in results)
    return {'status':'fail' if failed else 'pass','errors':errors,'fixtures':results,
            'scope':'Three isolated synthetic repetitions; no speech, acquisition, SD or concurrent-load acceptance.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference',type=Path,required=True)
    parser.add_argument('--run',type=Path,required=True)
    args=parser.parse_args()
    records=[]
    for name,pcm in pcm_fixtures().items():
        record=json.loads((args.reference/f'{name}.json').read_text())
        data=(args.reference/f'{name}.bin').read_bytes()
        if data!=struct.pack('<'+'h'*len(pcm),*pcm) or hashlib.sha256(data).hexdigest()!=record['sha256']:
            raise ValueError('Reference PCM identity mismatch')
        records.append(record)
    captures=[]
    for path in sorted((args.run/'captures').glob('*.json')):
        metadata=json.loads(path.read_text())
        if metadata.get('format')=='spectrum_f32le': captures.append(load_verified(path))
    result=assess_fixture_set(records,captures)
    summary=json.loads((args.run/'summary.json').read_text())
    if summary.get('capture_errors') or summary.get('integrity_errors') or summary.get('incomplete_captures'):
        result['errors'].append('Run/capture integrity errors; inspect original summary')
        result['status']='fail'
    with (args.run/'device-spectrum.json').open('x') as output:
        json.dump(result,output,indent=2);output.write('\n')
    print(json.dumps(result,indent=2))
    if result['status']!='pass': raise SystemExit(1)


if __name__=='__main__':main()
