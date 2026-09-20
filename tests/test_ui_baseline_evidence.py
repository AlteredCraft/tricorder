"""Animated UI acceptance depends on bounded, frame-linked panel submissions."""
import copy
import struct
import unittest
from tools.ui_baseline_evidence import compare_ui

class UiBaselineTests(unittest.TestCase):
    def setUp(self):
        self.rows=[(i+1,i+1,i*33000,i*33000+1000,i*33000+1500,0,0,100,100,0,1) for i in range(1819)]
        self.meta={'format':'ui_baseline_i64le','rows':1819,'columns':11,'duration_us':60000000,
                   'animation_period_ms':33,'refresh_period_ms':20,'missed_animation_deadlines':0,'generations':1819,'renders':1819,'submissions':1819,'observer_overflow':0,
                   'policy':'latest animation state per render; coalesced generations counted by host',
                   'cpu_before':{'total_ticks':1,'tasks':[{'id':1,'name':'lvgl','ticks':1,'stack_margin_bytes':3000}]},
                   'cpu_after':{'total_ticks':60000001,'tasks':[{'id':1,'name':'lvgl','ticks':6000001,'stack_margin_bytes':2500}]},
                   'memory_samples':[{'second':i+1,'free_internal':200000,'free_psram':20000000,'largest_psram':18000000,
                                      'stack_margin_bytes':2500,'free_task_sram':100000,'largest_task_sram':80000} for i in range(60)]}
    def result(self,meta=None,rows=None):
        return compare_ui(self.meta if meta is None else meta,b''.join(struct.pack('<11q',*r) for r in (self.rows if rows is None else rows)))
    def test_complete(self):
        r=self.result();self.assertEqual(r['status'],'pass');self.assertEqual(r['frames'],1819)
        self.assertEqual(r['coalesced_generations'],0);self.assertAlmostEqual(r['submitted_fps'],1e6/33000)
    def test_partial_flushes_are_one_frame(self):
        rows=[]
        for r in self.rows:rows.extend([(*r[:3],r[3]-200,r[3]-100,*r[5:10],0),r])
        meta=copy.deepcopy(self.meta);meta['rows']=meta['submissions']=len(rows)
        result=self.result(meta,rows);self.assertEqual(result['status'],'pass');self.assertEqual(result['frames'],1819)
    def test_coalesced_states_are_explicit(self):
        rows=[(r[0],r[1]*2,*r[2:]) for r in self.rows]
        meta=copy.deepcopy(self.meta);meta['generations']=3638
        r=self.result(meta,rows);self.assertEqual(r['status'],'pass');self.assertEqual(r['coalesced_generations'],1819)
    def test_missing_evidence_is_inconclusive(self):
        for key in ('cpu_before','memory_samples','submissions','policy'):
            meta=copy.deepcopy(self.meta);del meta[key]
            self.assertEqual(self.result(meta)['status'],'inconclusive',key)
    def test_errors_loss_stale_frame_and_latency_fail(self):
        for key,value in [('observer_overflow',1),('submissions',1820),('renders',1820),('duration_us',1000)]:
            meta=copy.deepcopy(self.meta);meta[key]=value;self.assertEqual(self.result(meta)['status'],'fail',key)
        for slot,value in [(9,-5),(10,0),(0,9999),(1,0),(2,999999)]:
            rows=self.rows.copy();r=list(rows[5]);r[slot]=value;rows[5]=tuple(r)
            self.assertEqual(self.result(rows=rows)['status'],'fail',slot)
        rows=[(*r[:3],r[3]+300000*(i>=5),r[4]+300000*(i>=5),*r[5:]) for i,r in enumerate(self.rows)]
        self.assertEqual(self.result(rows=rows)['status'],'fail')

    def test_requested_30fps_is_not_replaced_by_interval_limits(self):
        rows=[(i+1,i+1,i*35000,i*35000+1000,i*35000+1500,0,0,100,100,0,1) for i in range(1715)]
        meta=copy.deepcopy(self.meta)
        for key in ('rows','renders','submissions','generations'):meta[key]=1715
        self.assertEqual(self.result(meta,rows)['status'],'fail')
