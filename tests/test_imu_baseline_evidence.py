"""Polling evidence retains every attempt and must distinguish stale/error data."""
import copy
import struct
import unittest
from tools.imu_baseline_evidence import compare_imu

class ImuBaselineTests(unittest.TestCase):
    def setUp(self):
        self.rows=[(i+1,(i+1)*10000,(i+1)*10000,(i+1)*10000+700,0,((i+1)*256)&0xffffff,0xc0,1,2,3,4,5,6) for i in range(6000)]
        self.meta={'format':'imu_baseline_i32le','rows':6000,'columns':13,'period_us':10000,'duration_us':60000700,
                   'hardware_odr_hz':200,'accel_range_g':4,'gyro_range_dps':1000,'configuration_readback':True,
                   'policy':'latest-register-sample; intermediate hardware samples intentionally not retained',
                   'read_errors':0,'not_ready':0,'repeated_sensor_time':0,'missed_deadlines':0,
                   'cpu_before':{'total_ticks':1,'tasks':[{'id':1,'name':'main','ticks':1,'stack_margin_bytes':3000}]},
                   'cpu_after':{'total_ticks':60000001,'tasks':[{'id':1,'name':'main','ticks':6000001,'stack_margin_bytes':2500}]},
                   'memory_samples':[{'sample_index':(i+1)*100,'free_internal':200000,'free_psram':20000000,
                                      'largest_psram':18000000,'stack_margin_bytes':2500,'free_task_sram':100000,
                                      'largest_task_sram':80000} for i in range(60)]}
    def result(self,meta=None,rows=None):
        return compare_imu(self.meta if meta is None else meta,b''.join(struct.pack('<13i',*r) for r in (self.rows if rows is None else rows)))
    def test_complete_and_sensor_counter_wrap(self):
        result=self.result();self.assertEqual(result['status'],'pass');self.assertAlmostEqual(result['poll_hz'],100)
        self.assertEqual(result['read_duration_us']['max'],700)
        rows=[(*r[:5],(r[5]+0xffff00)&0xffffff,*r[6:]) for r in self.rows]
        self.assertEqual(self.result(rows=rows)['status'],'pass')
    def test_failure_and_stale_data_remain_failures(self):
        for index,value in [(0,99),(3,999999),(4,-7),(6,0x80)]:
            rows=self.rows.copy();r=list(rows[5]);r[index]=value;rows[5]=tuple(r)
            self.assertEqual(self.result(rows=rows)['status'],'fail')
        rows=self.rows.copy();r=list(rows[5]);r[5]=rows[4][5];rows[5]=tuple(r)
        self.assertEqual(self.result(rows=rows)['status'],'fail')
        meta=copy.deepcopy(self.meta);meta['read_errors']=1
        self.assertEqual(self.result(meta)['status'],'fail')
    def test_missing_instrumentation_is_inconclusive(self):
        for key in ('configuration_readback','cpu_after','memory_samples','policy'):
            meta=copy.deepcopy(self.meta);del meta[key]
            self.assertEqual(self.result(meta)['status'],'inconclusive',key)
        meta=copy.deepcopy(self.meta);del meta['cpu_after']['tasks'][0]['ticks']
        self.assertEqual(self.result(meta)['status'],'inconclusive')
    def test_incomplete_and_slow_run_fail(self):
        self.assertEqual(self.result(rows=self.rows[:-1])['status'],'fail')
        meta=copy.deepcopy(self.meta);meta['duration_us']=120000000
        self.assertEqual(self.result(meta)['status'],'fail')

    def test_deadlines_also_reject_early_bursts_and_overlapping_reads(self):
        rows=self.rows.copy();row=list(rows[5]);row[2]=row[1]-2000;rows[5]=tuple(row)
        self.assertEqual(self.result(rows=rows)['status'],'fail')
        rows=self.rows.copy();row=list(rows[4]);row[3]=self.rows[5][2]+1;rows[4]=tuple(row)
        self.assertEqual(self.result(rows=rows)['status'],'fail')
