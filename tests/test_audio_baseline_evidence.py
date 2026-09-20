"""Require complete 60-second audio timing/counter evidence, not a firmware pass label."""
import copy
import struct
import unittest
from tools.audio_baseline_evidence import compare_baseline

class AudioBaselineEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.rows=[(10000*(n+1),10000*(n+1)+700,650,int((n+1)%5==0)) for n in range(6000)]
        self.meta={'format':'audio_baseline_u32le','rows':6000,'columns':4,'sample_rate_hz':48000,
                   'block_frames':480,'raw_channels':4,'speech_rate_hz':16000,'speech_frames':960000,
                   'fft_frames':2048,'fft_hop_frames':2400,'fft_count':1200,'raw_frames':2880000,
                   'read_bytes':23040000,'dma_bytes':23040000,'overflows':0,'overwritten_bytes':0,
                   'short_reads':0,'read_errors':0,'raw_mutations':0,'duration_us':60000700,
                   'memory_samples':[{'block_index':(n+1)*100,'free_internal':100000,'free_psram':20000000,
                                      'largest_internal':50000,'largest_psram':19000000,'stack_margin_bytes':2000} for n in range(60)],
                   'cpu_before':{'total_ticks':100,'tasks':[{'id':1,'name':'IDLE0','ticks':0},{'id':2,'name':'IDLE1','ticks':0}]},
                   'cpu_after':{'total_ticks':60000100,'tasks':[{'id':1,'name':'IDLE0','ticks':30000000},{'id':2,'name':'IDLE1','ticks':40000000}]}}
    def result(self,meta=None,rows=None):
        data=b''.join(struct.pack('<4I',*r) for r in (self.rows if rows is None else rows))
        return compare_baseline(self.meta if meta is None else meta,data)
    def test_complete_run(self):
        result=self.result();self.assertEqual(result['status'],'pass',result)
        self.assertAlmostEqual(result['sample_rate_observed_hz'],47999.4400065,places=6)
    def test_missing_and_loss(self):
        for key in ('memory_samples','cpu_before','read_errors'):
            meta=copy.deepcopy(self.meta);del meta[key]
            self.assertEqual(self.result(meta)['status'],'inconclusive')
        for key,value in [('fft_count',1199),('overflows',1),('read_bytes',23039992),('raw_mutations',1)]:
            meta=copy.deepcopy(self.meta);meta[key]=value
            self.assertEqual(self.result(meta)['status'],'fail',key)
        self.assertEqual(self.result(rows=self.rows[:-1])['status'],'fail')
    def test_time_and_fft_cadence(self):
        for row in ((1,2,1,0),(20000,20700,650,1)):
            rows=self.rows.copy();rows[1]=row
            self.assertEqual(self.result(rows=rows)['status'],'fail')
