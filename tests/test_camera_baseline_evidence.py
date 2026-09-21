"""Camera baseline checks must account for callbacks, buffer starvation and frame identity."""
import copy
import struct
import unittest
from tools.camera_baseline_evidence import compare_camera

class CameraBaselineEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.rows=[(11+i,(i+1)*33334,(i+1)*33334+50,(i+1)*33334+80,1843200) for i in range(1800)]
        self.meta={'format':'camera_baseline_u64le','rows':1800,'columns':5,'width':1280,'height':720,
                   'frame_bytes':1843200,'duration_us':60002000,'completed_before':10,'completed_after':1810,
                   'missing_buffers':0,'untracked_buffers':0,'reused_completions':0,'completed_bytes':1800*1843200,
                   'completed_at_stop_request':1810,
                   'discarded_completed_at_stop':0,'cpu_before':{'total_ticks':1,'tasks':[{'id':1,'name':'main','ticks':1,'stack_margin_bytes':2000}]},
                   'cpu_after':{'total_ticks':60000001,'tasks':[{'id':1,'name':'main','ticks':600001,'stack_margin_bytes':1800}]},
                   'memory_samples':[{'frame_index':(n+1)*30,'free_internal':200000,'free_psram':20000000,
                                      'largest_psram':18000000,'stack_margin_bytes':2000,
                                      'free_task_sram':150000,'largest_task_sram':100000} for n in range(60)]}
    def result(self,meta=None,rows=None):
        return compare_camera(self.meta if meta is None else meta,b''.join(struct.pack('<5Q',*r) for r in (self.rows if rows is None else rows)))
    def test_complete(self):self.assertEqual(self.result()['status'],'pass')
    def test_missing_is_inconclusive(self):
        for key in ('missing_buffers','cpu_before','memory_samples','reused_completions','completed_at_stop_request'):
            meta=copy.deepcopy(self.meta);del meta[key]
            self.assertEqual(self.result(meta)['status'],'inconclusive',key)
    def test_hidden_loss_and_frame_gaps_fail(self):
        for key,value in [('missing_buffers',1),('completed_after',1811),('completed_bytes',1),('duration_us',1000)]:
            meta=copy.deepcopy(self.meta);meta[key]=value
            self.assertEqual(self.result(meta)['status'],'fail',key)
        rows=self.rows.copy();rows[5]=(999,*rows[5][1:])
        self.assertEqual(self.result(rows=rows)['status'],'fail')
        rows=self.rows.copy();rows[5]=(16,199999,199998,200000,1843200)
        self.assertEqual(self.result(rows=rows)['status'],'fail')
    def test_explicit_tail_is_bounded(self):
        meta=copy.deepcopy(self.meta);meta['completed_after']+=1;meta['discarded_completed_at_stop']=1;meta['completed_bytes']+=1843200
        self.assertEqual(self.result(meta)['status'],'pass')
        meta['completed_after']+=5;meta['discarded_completed_at_stop']+=5;meta['completed_bytes']+=5*1843200
        self.assertEqual(self.result(meta)['status'],'fail')

    def test_reused_completion_and_pre_stop_tail_are_not_waived(self):
        meta=copy.deepcopy(self.meta);meta['reused_completions']=1
        self.assertEqual(self.result(meta)['status'],'fail')
        meta=copy.deepcopy(self.meta)
        meta.update(completed_after=1811,completed_at_stop_request=1811,
                    discarded_completed_at_stop=1,completed_bytes=1801*1843200)
        self.assertEqual(self.result(meta)['status'],'fail')

    def test_resource_evidence_cannot_be_placeholder(self):
        for section,key in [('cpu_before','total_ticks'),('cpu_after','total_ticks')]:
            meta=copy.deepcopy(self.meta);del meta[section][key]
            self.assertEqual(self.result(meta)['status'],'inconclusive')
        meta=copy.deepcopy(self.meta);del meta['cpu_after']['tasks'][0]['ticks']
        self.assertEqual(self.result(meta)['status'],'inconclusive')
        meta=copy.deepcopy(self.meta);del meta['memory_samples'][0]['free_task_sram']
        self.assertEqual(self.result(meta)['status'],'inconclusive')
        meta=copy.deepcopy(self.meta);meta['cpu_after']['total_ticks']=meta['cpu_before']['total_ticks']
        self.assertEqual(self.result(meta)['status'],'fail')
        result=self.result()
        self.assertAlmostEqual(result['cpu_tasks'][0]['runtime_fraction_of_wall'],.01)
        self.assertEqual(result['cpu_tasks'][0]['stack_margin_bytes'],1800)
        self.assertEqual(result['memory_min']['free_task_sram'],150000)
