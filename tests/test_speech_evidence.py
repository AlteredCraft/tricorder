import copy
import hashlib
import struct
import unittest

from tools.audio_reference import pcm_fixtures
from tools.speech_evidence import compare_pair, speech_reference


class SpeechEvidenceTests(unittest.TestCase):
    def fixture(self, enabled=True):
        name='tone_bin_37';samples=pcm_fixtures()[name]
        raw=struct.pack('<2048h',*samples)
        blocks=[]
        for start in range(0,2048,480):
            data=raw[start*2:min(start+480,2048)*2]
            blocks.append({'source_start_frame':start,'frames':len(data)//2,
                           'sha256':hashlib.sha256(data).hexdigest()})
        digest=hashlib.sha256(raw).hexdigest()
        raw_meta={'capture_id':'raw-1','boot_id':'boot-a','fixture_id':name,'repetition':1,
                  'speech_enabled':enabled,'role':'measurement_replay','format':'pcm_s16le',
                  'sample_rate_hz':48000,'channels':1,'frames':2048,
                  'input_sha256_before':digest,'input_sha256_after':digest,'ingress_blocks':blocks}
        output=speech_reference(samples,enabled)
        speech=struct.pack('<'+'h'*len(output),*output)
        speech_meta={'boot_id':'boot-a','fixture_id':name,'repetition':1,'speech_enabled':enabled,
                     'role':'speech_replay','format':'pcm_s16le','channels':1,'frames':len(output),
                     'sample_rate_hz':16000 if enabled else 48000,'source_capture_id':'raw-1',
                     'source_start_frame':0,'source_frames':2048,'compute_us':1200,
                     'input_clipped':0,'output_clipped':0,
                     'processing':'dc80-fir63-fc6500-decimate3-v1' if enabled else 'selected-slot-copy-v1'}
        return raw_meta,raw,speech_meta,speech

    def test_independent_reference_enabled_and_disabled(self):
        for enabled in (True,False):
            self.assertEqual(compare_pair(*self.fixture(enabled))['status'],'pass')

    def test_raw_changes_or_missing_ingress_ranges_fail(self):
        raw_meta,raw,speech_meta,speech=self.fixture()
        changed=bytearray(raw);changed[20]^=1
        self.assertEqual(compare_pair(raw_meta,bytes(changed),speech_meta,speech)['status'],'fail')
        for alteration in ('missing','hash','offset'):
            altered=copy.deepcopy(raw_meta)
            if alteration=='missing':altered['ingress_blocks'].pop()
            elif alteration=='hash':altered['ingress_blocks'][1]['sha256']='wrong'
            else:altered['ingress_blocks'][1]['source_start_frame']+=1
            self.assertEqual(compare_pair(altered,raw,speech_meta,speech)['status'],'fail')

    def test_wrong_link_boot_processing_or_output_fails(self):
        raw_meta,raw,speech_meta,speech=self.fixture()
        for field,value in [('source_capture_id','wrong'),('boot_id','wrong'),
                            ('source_frames',2047),('processing','unknown'),('sample_rate_hz',48000),('input_clipped',1)]:
            altered=dict(speech_meta);altered[field]=value
            self.assertEqual(compare_pair(raw_meta,raw,altered,speech)['status'],'fail',field)
        self.assertEqual(compare_pair(raw_meta,raw,speech_meta,bytes(len(speech)))['status'],'fail')
