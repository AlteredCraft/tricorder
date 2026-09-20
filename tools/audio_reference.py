"""Independent direct-DFT reference and deterministic PCM fixtures for G-0001.03."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import struct


def spectrum(samples, sample_rate):
    size = len(samples)
    if not 8 <= size <= 4096 or size & (size-1):
        raise ValueError('reference requires a power-of-two block of 8..4096 samples')
    if type(sample_rate) is not int or sample_rate <= 0:
        raise ValueError('invalid sample rate')
    if any(not math.isfinite(x) or not -1 <= x <= 1 for x in samples):
        raise ValueError('samples must be finite normalized PCM')
    window = [.5-.5*math.cos(2*math.pi*n/size) for n in range(size)]
    window_sum = math.fsum(window)
    weighted = [x*w for x,w in zip(samples,window)]
    amplitude = []
    # Deliberately direct sums, independent of the device FFT implementation.
    for k in range(size//2+1):
        angle = 2*math.pi*k/size
        real = math.fsum(x*math.cos(angle*n) for n,x in enumerate(weighted))
        imaginary = math.fsum(-x*math.sin(angle*n) for n,x in enumerate(weighted))
        factor = 1 if k in (0,size//2) else 2
        amplitude.append(factor*math.hypot(real,imaginary)/window_sum)
    peak = max(range(len(amplitude)),key=amplitude.__getitem__)
    # A spectral maximum below the comparison floor is not a frequency estimate.
    floor = 1e-6
    ties = sum(abs(value-amplitude[peak]) <= 1e-12 for value in amplitude)
    unique_peak = amplitude[peak] >= floor and ties == 1
    return {'sample_rate_hz':sample_rate, 'frames':size, 'window':'periodic Hann',
            'normalization':'one-sided amplitude / sum(window); DC and Nyquist undoubled',
            'pcm_scale':'signed PCM16 / 32768', 'amplitude_floor_fs':floor,
            'bin_width_hz':sample_rate/size, 'amplitude_fs':amplitude,
            'peak_bin':peak if unique_peak else None,
            'peak_hz':peak*sample_rate/size if unique_peak else None,
            'peak_tie_bins':ties, 'peak_tie_tolerance_fs':1e-12,
            'peak_amplitude_fs':amplitude[peak]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    size,rate = 2048,48000
    fixtures = {
        'tone_bin_37':[.25*math.sin(2*math.pi*37*n/size) for n in range(size)],
        'mixture_37_131':[.25*math.sin(2*math.pi*37*n/size)
                          +.125*math.sin(2*math.pi*131*n/size) for n in range(size)],
        'silence':[0.0]*size,
        'impulse_center':[.5 if n==size//2 else 0.0 for n in range(size)]}
    results = []
    for name,samples in fixtures.items():
        pcm = [max(-32768,min(32767,round(x*32768))) for x in samples]
        payload = struct.pack('<'+'h'*len(pcm),*pcm)
        digest = hashlib.sha256(payload).hexdigest()
        (args.output/f'{name}.bin').write_bytes(payload)
        reference = spectrum([x/32768 for x in pcm],rate)
        record = {'fixture_id':name,'format':'pcm_s16le','channels':1,
                  'size_bytes':len(payload),'sha256':digest,'reference':reference,
                  'device_comparison':'inconclusive; no device output supplied',
                  'clipped_samples':sum(x in (-32768,32767) for x in pcm)}
        (args.output/f'{name}.json').write_text(json.dumps(record,indent=2)+'\n')
        results.append({'fixture_id':name,'sha256':digest,'peak_hz':reference['peak_hz'],
                        'peak_amplitude_fs':reference['peak_amplitude_fs']})
    (args.output/'manifest.json').write_text(json.dumps({
        'spec_id':'G-0001.03', 'created_utc':datetime.now(timezone.utc).isoformat(),
        'generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'scope':'Synthetic host reference only; not microphone or device DSP evidence.',
        'fixtures':results},indent=2)+'\n')
    (args.output/'summary.json').write_text(json.dumps({
        'status':'inconclusive', 'host_fixtures_generated':len(results),
        'device_dsp':'not tested','raw_speech_separation':'not tested',
        'sd_readback':'not tested','acoustic_load':'not tested'},indent=2)+'\n')
    print(json.dumps(results,indent=2))


if __name__ == '__main__':
    main()
