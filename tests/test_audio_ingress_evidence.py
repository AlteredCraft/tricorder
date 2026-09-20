"""Reject missing or inconsistent acquisition accounting independently of firmware checks."""
import copy
import unittest
from tools.audio_ingress_evidence import assess_ingress


class IngressEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.record={'event':'audio_ingress','boot_id':'boot','capture_id':'boot-audio-0',
                     'requested_bytes':1152000,'acquisition_start_us':1000000,'acquisition_end_us':4000000}
        for counter in ('read_bytes','dma_bytes','overwritten_bytes','overflows','short_reads','read_errors'):
            self.record[counter+'_before']=0
            self.record[counter+'_after']=1152000 if counter in ('read_bytes','dma_bytes') else 0
        self.meta={'boot_id':'boot','capture_id':'boot-audio-0','format':'pcm_s16le',
                   'channels':4,'sample_rate_hz':48000,'frames':144000,'driver_epoch_integrity':True,
                   'acquisition_start_us':1000000,'acquisition_end_us':4000000}
        self.captures={'boot-audio-0':(self.meta,1152000)}

    def result(self,records=None,captures=None):
        return assess_ingress([self.record] if records is None else records,
                              self.captures if captures is None else captures)

    def test_exact_epoch_and_prior_loss(self):
        self.assertEqual(self.result()['status'],'pass')
        self.record['overflows_before']=self.record['overflows_after']=3
        self.record['overwritten_bytes_before']=self.record['overwritten_bytes_after']=5760
        self.assertEqual(self.result()['status'],'pass')

    def test_missing_and_bad_counters(self):
        for field in ('read_bytes_after','dma_bytes_before','short_reads_after'):
            record=copy.deepcopy(self.record);del record[field]
            self.assertEqual(self.result([record])['status'],'fail')
        for field,value in [('read_bytes_after',1151998),('dma_bytes_after',100),('overflows_after',1),
                            ('read_errors_after',1),('short_reads_after',True),('read_bytes_before',-1)]:
            record=copy.deepcopy(self.record);record[field]=value
            self.assertEqual(self.result([record])['status'],'fail')
        self.assertEqual(self.result([])['status'],'inconclusive')

    def test_capture_identity_format_and_range(self):
        for field,value in [('boot_id','other'),('frames',143999),('sample_rate_hz',16000),
                            ('acquisition_start_us',1000001),('driver_epoch_integrity',False)]:
            meta=copy.deepcopy(self.meta);meta[field]=value
            self.assertEqual(self.result(captures={'boot-audio-0':(meta,1152000)})['status'],'fail')
        self.assertEqual(self.result(captures={})['status'],'fail')
        self.assertEqual(self.result(captures={'boot-audio-0':(self.meta,1151999)})['status'],'fail')

    def test_duplicates_and_lifetime_counter_rollback(self):
        self.assertEqual(self.result([self.record,self.record])['status'],'fail')
        record=copy.deepcopy(self.record);record['capture_id']='boot-audio-1'
        record['acquisition_start_us']=5000000;record['acquisition_end_us']=8000000
        meta=copy.deepcopy(self.meta);meta.update({key:record[key] for key in ('capture_id','acquisition_start_us','acquisition_end_us')})
        captures={**self.captures,'boot-audio-1':(meta,1152000)}
        self.assertEqual(self.result([self.record,record],captures)['status'],'fail')
        for field in ('read_bytes','dma_bytes'):
            record[field+'_before']=1152000;record[field+'_after']=2304000
        self.assertEqual(self.result([self.record,record],captures)['status'],'pass')
