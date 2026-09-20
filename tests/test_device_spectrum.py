import copy
import hashlib
import math
import struct
import unittest

from tools.audio_reference import spectrum
from tools.device_spectrum import compare_fixture, assess_fixture_set


class DeviceSpectrumTests(unittest.TestCase):
    def fixture(self):
        pcm=struct.pack('<8h',*[round(8192*math.sin(2*math.pi*n/8)) for n in range(8)])
        reference=spectrum([x/32768 for x in struct.unpack('<8h',pcm)],48000)
        record={'fixture_id':'tone','sha256':hashlib.sha256(pcm).hexdigest(),
                'reference':reference,'clipped_samples':0}
        metadata={'format':'spectrum_f32le','fixture_id':'tone','frames':8,'sample_rate_hz':48000,
                  'window':reference['window'],'normalization':reference['normalization'],
                  'pcm_scale':reference['pcm_scale'],'input_sha256_before':record['sha256'],
                  'input_sha256_after':record['sha256'],'clipped_samples':0,'compute_us':100,
                  'peak_bin':reference['peak_bin'],'peak_amplitude_fs':reference['peak_amplitude_fs']}
        data=struct.pack('<5f',*reference['amplitude_fs'])
        return record,metadata,data

    def test_full_spectrum_and_input_identity_match(self):
        record,metadata,data=self.fixture()
        self.assertEqual(compare_fixture(record,metadata,data)['status'],'pass')

    def test_wrong_fixture_changed_raw_or_conventions_fail(self):
        record,metadata,data=self.fixture()
        for field,value in [('fixture_id','wrong'),('input_sha256_after','bad'),
                            ('input_sha256_before','bad'),('window','rectangular'),
                            ('frames',16),('sample_rate_hz',44100),('clipped_samples',1),
                            ('compute_us',-1),('peak_bin',4),('peak_amplitude_fs',0.1)]:
            altered=copy.deepcopy(metadata);altered[field]=value
            self.assertEqual(compare_fixture(record,altered,data)['status'],'fail',field)

    def test_full_vector_nan_short_or_wrong_bins_fail(self):
        record,metadata,data=self.fixture()
        for changed in (data[:-4],struct.pack('<5f',float('nan'),0,0,0,0),
                        struct.pack('<5f',0,0,0,0,0), data+data):
            self.assertEqual(compare_fixture(record,metadata,changed)['status'],'fail')

    def test_set_requires_every_repetition_once_from_one_boot(self):
        record,metadata,data=self.fixture()
        captures=[(dict(metadata,repetition=i,boot_id='boot-a'),data) for i in (1,2,3)]
        self.assertEqual(assess_fixture_set([record],captures)['status'],'pass')
        for altered in (captures[:-1],captures+[captures[0]],
                        captures[:2]+[(dict(captures[2][0],boot_id='other'),data)]):
            self.assertEqual(assess_fixture_set([record],altered)['status'],'fail')
