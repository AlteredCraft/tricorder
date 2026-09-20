"""Independent live raw/speech checks reject altered raw data and broken provenance."""
import copy
import hashlib
import struct
import unittest
from tools.live_audio_evidence import compare_live
from tools.speech_evidence import speech_reference


class LiveAudioEvidenceTests(unittest.TestCase):
    def setUp(self):
        samples=[int(2000*((i%31)-15)/15) for i in range(30)]
        self.raw=struct.pack('<'+'h'*120,*[value for sample in samples for value in (sample,0,-sample,1)])
        output=speech_reference(samples,True)
        self.speech=struct.pack('<'+'h'*len(output),*output)
        blocks=[]
        for start in (0,10,20):
            blocks.append({'source_start_frame':start,'frames':10,
                           'sha256':hashlib.sha256(self.raw[start*8:(start+10)*8]).hexdigest(),
                           'raw_unchanged':True,'read_end_us':1000+start*100,'speech_ready_us':1020+start*100,'speech_compute_us':15,
                           'clipped_samples':[0,0,0,0]})
        self.meta={'capture_id':'boot-audio-0','boot_id':'boot','format':'pcm_s16le','channels':4,
                   'frames':30,'sample_rate_hz':48000,'gain_db':24,'driver_epoch_integrity':True,
                   'acquisition_start_us':500,'acquisition_end_us':4000,'ingress_blocks':blocks}
        self.derived={'capture_id':'boot-audio-0-speech','boot_id':'boot','source_capture_id':'boot-audio-0',
                      'format':'pcm_s16le','channels':1,'frames':10,'sample_rate_hz':16000,
                      'source_slot':0,'source_start_frame':0,'source_frames':30,'input_clipped':0,'output_clipped':0,
                      'processing':'dc80-fir63-fc6500-decimate3-v1','role':'speech_live','compute_us':45}

    def result(self,meta=None,raw=None,derived=None,speech=None):
        return compare_live(self.meta if meta is None else meta,self.raw if raw is None else raw,
                            self.derived if derived is None else derived,self.speech if speech is None else speech)

    def test_independent_live_comparison(self):
        result=self.result()
        self.assertEqual(result['status'],'pass',result)
        self.assertEqual(result['max_sample_error_counts'],0)
        self.assertEqual(result['blocks'],3)

    def test_gaps_overlap_and_raw_mutation(self):
        for mode in ('missing','offset','hash','unchanged','clip','time','ready'):
            meta=copy.deepcopy(self.meta)
            if mode=='missing':meta['ingress_blocks'].pop()
            if mode=='offset':meta['ingress_blocks'][1]['source_start_frame']=9
            if mode=='hash':meta['ingress_blocks'][1]['sha256']='bad'
            if mode=='unchanged':meta['ingress_blocks'][1]['raw_unchanged']=False
            if mode=='clip':meta['ingress_blocks'][1]['clipped_samples']=[1,0,0,0]
            if mode=='time':meta['ingress_blocks'][1]['read_end_us']=999
            if mode=='ready':meta['ingress_blocks'][1]['speech_ready_us']=1999
            self.assertEqual(self.result(meta=meta)['status'],'fail',mode)
        raw=bytes([self.raw[0]^1])+self.raw[1:]
        self.assertEqual(self.result(raw=raw)['status'],'fail')

    def test_source_metadata_and_output_rejected(self):
        for field,value in [('boot_id','other'),('source_slot',4),('source_frames',29),
                            ('source_capture_id','other'),('processing','unknown'),('compute_us',44),
                            ('input_clipped',1),('sample_rate_hz',48000)]:
            derived=copy.deepcopy(self.derived);derived[field]=value
            self.assertEqual(self.result(derived=derived)['status'],'fail',field)
        self.assertEqual(self.result(speech=self.speech[:-2])['status'],'fail')
        self.assertEqual(self.result(speech=b'\xff\x7f'*10)['status'],'fail')
        meta=copy.deepcopy(self.meta);meta['driver_epoch_integrity']=False
        self.assertEqual(self.result(meta=meta)['status'],'fail')
