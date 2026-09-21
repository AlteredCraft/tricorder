import copy
import struct
import unittest

from tools.preview_evidence import assess_preview, verify_preview_witness, POLICY


class PreviewEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.camera=[(i+11,(i+1)*33333,(i+1)*33333+100,(i+1)*33333+3000,1843200) for i in range(1800)]
        self.frames=[(i+1,c[0],c[1],c[2],c[2]+1,c[2]+1000,c[2]+1500,0) for i,c in enumerate(self.camera[1::2])]
        self.ui=[(i+1,i+1,r[6],r[6]+1000,r[6]+1100,0,0,640,360,0,1) for i,r in enumerate(self.frames)]
        self.meta=dict(format='preview_frames_i64le',columns=8,rows=900,width=640,height=360,
                       buffer_count=3,buffer_bytes=460800,camera_frames=1800,throttled_frames=900,
                       produced=900,selected=900,pending_replaced=0,pending_end=0,busy_drops=0,copy_errors=0,
                       acquisition_start_us=1000000,duration_us=60200000,policy=POLICY,
                       resize='nearest RGB565 top-left pixel of each 2x2 source block')
        self.ui_meta=dict(format='preview_submissions_i64le',columns=11,rows=900,renders=900,observer_overflow=0,
                          acquisition_start_us=1000000,duration_us=60200000)
    def result(self):
        pack=lambda rows,n:b''.join(struct.pack('<'+str(n)+'q',*r) for r in rows)
        return assess_preview(self.meta,pack(self.frames,8),self.ui_meta,pack(self.ui,11),self.camera,1000000)
    def test_complete_source_to_panel_chain(self):
        r=self.result();self.assertEqual(r['status'],'pass');self.assertEqual(r['displayed_previews'],900)
        self.assertFalse(r['animated_ui_acceptance'])
    def test_pending_replacement_and_render_coalescing_are_counted(self):
        self.frames[5]=(*self.frames[5][:6],0,0)
        self.meta['selected']-=1;self.meta['pending_replaced']+=1
        self.ui.pop(5);self.ui=[(i+1,*r[1:]) for i,r in enumerate(self.ui)]
        self.ui_meta['rows']=self.ui_meta['renders']=899
        r=self.result();self.assertEqual(r['status'],'pass');self.assertEqual(r['pending_replaced'],1)
        self.ui.pop(5);self.ui=[(i+1,*r[1:]) for i,r in enumerate(self.ui)]
        self.ui_meta['rows']=self.ui_meta['renders']=898
        self.assertEqual(self.result()['selected_but_not_rendered'],1)
    def test_missing_instrumentation_never_passes(self):
        for key in ('selected','policy','buffer_count','duration_us'):
            original=self.meta.copy();del self.meta[key]
            self.assertEqual(self.result()['status'],'inconclusive',key);self.meta=original
    def test_unaccounted_stale_bad_results_and_stalls_fail(self):
        for field,value in [(1,99),(2,1),(5,1),(6,0),(7,-1)]:
            old=self.frames[4];r=list(old);r[field]=value;self.frames[4]=tuple(r)
            self.assertEqual(self.result()['status'],'fail',field);self.frames[4]=old
        old=self.ui[4];self.ui[4]=(*old[:3],old[3]+300000,old[4]+300000,*old[5:])
        self.assertEqual(self.result()['status'],'fail');self.ui[4]=old
        self.meta['pending_end']=1;self.assertEqual(self.result()['status'],'fail')
    def test_partial_flushes_count_as_one_render(self):
        self.ui=[part for r in self.ui for part in [(*r[:3],r[3]-100,r[3]-50,*r[5:10],0),r]]
        self.ui_meta['rows']=len(self.ui)
        self.assertEqual(self.result()['displayed_previews'],900)
    def test_copy_must_finish_before_native_buffer_requeue(self):
        camera=list(self.camera[9]);camera[3]=self.frames[4][5]-1;self.camera[9]=tuple(camera)
        self.assertEqual(self.result()['status'],'fail')
    def test_independent_downsample_witness(self):
        raw=bytes(range(32));raw_meta=dict(format='rgb565le',width=4,height=4,completion_sequence=99)
        small=bytes([0,1,4,5,16,17,20,21]);meta=dict(format='rgb565le',width=2,height=2,source_sequence=99)
        verify_preview_witness(meta,small,raw_meta,raw)
        for bad in (small[:-1],bytes(8)):
            with self.assertRaises(ValueError):verify_preview_witness(meta,bad,raw_meta,raw)
        meta['source_sequence']=98
        with self.assertRaises(ValueError):verify_preview_witness(meta,small,raw_meta,raw)
