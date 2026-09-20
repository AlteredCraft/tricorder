"""Verify retained bytes, then render a camera PNG or per-slot PCM WAV files."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
import wave


def load_verified(path):
    metadata = json.loads(path.read_text())
    if metadata.get('status') != 'complete':
        raise ValueError('capture is not complete')
    data = path.with_suffix('.bin').read_bytes()
    if len(data) != metadata['size_bytes'] or hashlib.sha256(data).hexdigest() != metadata['sha256']:
        raise ValueError('saved capture size or digest mismatch')
    return metadata, data


def split_pcm(data, channels):
    if type(channels) is not int or not 1 <= channels <= 16 or len(data) % (2*channels):
        raise ValueError('invalid interleaved PCM frame layout')
    values = struct.unpack('<'+'h'*(len(data)//2), data)
    return [values[slot::channels] for slot in range(channels)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('metadata', type=Path)
    args = parser.parse_args()
    metadata, data = load_verified(args.metadata)
    output = args.metadata.with_name(args.metadata.stem+'-view')
    output.mkdir(exist_ok=False)
    result = {'source': str(args.metadata), 'source_sha256': metadata['sha256'], 'format': metadata['format']}
    if metadata['format'] == 'rgb565le':
        width, height = metadata['width'], metadata['height']
        stride = metadata.get('stride_bytes') or width*2
        if type(width) is not int or type(height) is not int or min(width,height) <= 0:
            raise ValueError('invalid camera dimensions')
        if stride != width*2 or len(data) != stride*height:
            raise ValueError('camera layout differs from packed RGB565; inspect before converting')
        subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-n', '-f', 'rawvideo',
                        '-pixel_format', 'rgb565le', '-video_size', f'{width}x{height}',
                        '-i', str(args.metadata.with_suffix('.bin')), '-frames:v', '1',
                        str(output/'camera.png')], check=True)
        result.update(width=width, height=height, preview=str(output/'camera.png'))
    elif metadata['format'] == 'pcm_s16le':
        slots = split_pcm(data, metadata['channels'])
        if not slots[0] or len(slots[0]) != metadata['frames']:
            raise ValueError('PCM sample count mismatch')
        result['slots'] = []
        for slot, samples in enumerate(slots):
            path = output/f'slot-{slot}.wav'
            with wave.open(str(path), 'wb') as out:
                out.setnchannels(1)
                out.setsampwidth(2)
                out.setframerate(metadata['sample_rate_hz'])
                out.writeframes(struct.pack('<'+'h'*len(samples), *samples))
            result['slots'].append({'slot':slot, 'wav':str(path), 'samples':len(samples),
                                    'min':min(samples), 'max':max(samples),
                                    'clipped_samples':sum(x in (-32768,32767) for x in samples),
                                    'rms_counts':math.sqrt(sum(x*x for x in samples)/len(samples))})
        result['limit'] = 'Digital counts, not calibrated SPL; physical slot mapping remains unverified.'
    else:
        raise ValueError('unsupported capture format')
    (output/'inspection.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
