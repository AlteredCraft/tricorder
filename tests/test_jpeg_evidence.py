"""Fresh JPEG records must join camera provenance, hash boundaries and bounded timings."""
import copy,unittest
from tools.jpeg_evidence import assess_records
class JpegEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.rows=[{'index':i+1,'source_sequence':(i+1)*60,'source_completed_us':(i+1)*2000000,
                    'dequeued_us':(i+1)*2000000+100,'copied_us':(i+1)*2000000+2000,
                    'source_hash_start_us':(i+1)*2000000+200,'source_hash_end_us':(i+1)*2000000+1500,
                    'copy_start_us':(i+1)*2000000+1600,
                    'encode_start_us':(i+1)*2000000+3000,'encode_end_us':(i+1)*2000000+15000,
                    'source_sha256':'a'*64,'copy_sha256':'a'*64,'after_sha256':'a'*64,'jpeg_bytes':120000,
                    'result':0} for i in range(30)]
        self.meta={'width':1280,'height':720,'quality':75,'subsampling':'YUV420','source_format':'rgb565le',
                   'source_bytes':1843200,'attempts':30,'busy_drops':0,'pool_overflows':0,'output_capacity':1843200,
                   'pool_capacity':6291456,'records':self.rows,'epoch_start_us':1000000}
        self.camera={r['source_sequence']:(r['source_completed_us'],r['dequeued_us']) for r in self.rows}
    def test_complete(self):self.assertEqual(assess_records(self.meta,self.camera)['status'],'pass')
    def test_errors_stale_and_mutated_source_fail(self):
        for key,value in [('result',-1),('copy_sha256','b'*64),('after_sha256','b'*64),('source_sequence',9),
                          ('copied_us',99999999),('jpeg_bytes',2000000),('source_completed_us',1)]:
            m=copy.deepcopy(self.meta);m['records'][4][key]=value
            self.assertEqual(assess_records(m,self.camera)['status'],'fail',key)
        for key,value in [('busy_drops',1),('pool_overflows',1),('attempts',29)]:
            m=copy.deepcopy(self.meta);m[key]=value;self.assertEqual(assess_records(m,self.camera)['status'],'fail')
    def test_missing_instrumentation_is_inconclusive(self):
        m=copy.deepcopy(self.meta);del m['busy_drops'];self.assertEqual(assess_records(m,self.camera)['status'],'inconclusive')
        m=copy.deepcopy(self.meta);m['records']=m['records'][:-1];self.assertEqual(assess_records(m,self.camera)['status'],'fail')

    def test_source_hash_and_copy_have_separate_observed_timings(self):
        result=assess_records(self.meta,self.camera)
        self.assertEqual(result['source_hash_us']['max'],1300)
        self.assertEqual(result['source_copy_us']['max'],400)
        m=copy.deepcopy(self.meta);del m['records'][0]['copy_start_us']
        self.assertEqual(assess_records(m,self.camera)['status'],'inconclusive')
        m=copy.deepcopy(self.meta);m['records'][0]['source_hash_end_us']=m['records'][0]['copied_us']+1
        self.assertEqual(assess_records(m,self.camera)['status'],'fail')

    def test_jpeg_run_requires_independent_camera_assessment(self):
        import struct
        from tools.jpeg_evidence import assess_run
        data=b''.join(struct.pack('<5Q',r['source_sequence'],r['source_completed_us'],
                                  r['dequeued_us'],r['copied_us'],1843200) for r in self.rows)
        camera={'format':'camera_baseline_u64le','rows':30,'columns':5}
        # JPEG records join perfectly and the device check passed, but camera
        # continuity/resource evidence is missing and acquisition has gaps.
        result=assess_run(self.meta,camera,data,{'status':'pass'})
        self.assertEqual(result['status'],'fail')
        self.assertIn('Independent camera baseline did not pass',result['errors'])

class JpegProvenanceTests(unittest.TestCase):
    def test_settings_identity_and_retained_source_witness(self):
        import hashlib
        from tools.jpeg_evidence import verify_image_record,verify_witness
        data=b'raw source';sha=hashlib.sha256(data).hexdigest()
        baseline={'boot_id':'boot','epoch_start_us':10,'width':1280,'height':720,'quality':75,'subsampling':'YUV420'}
        record={'source_sequence':99,'source_completed_us':20,'source_sha256':sha,'jpeg_bytes':2}
        image={'format':'jpeg','boot_id':'boot','source_sequence':99,'source_completed_device_us':30,'source_sha256':sha,
               'width':1280,'height':720,'quality':75,'subsampling':'YUV420'}
        verify_image_record(image,b'xx',record,baseline)
        witness={'completion_sequence':99,'sha256':sha,'format':'rgb565le'}
        verify_witness(record,witness,data)
        for key,value in [('quality',50),('source_sequence',100),('source_completed_device_us',31),('boot_id','old')]:
            bad=image.copy();bad[key]=value
            with self.assertRaises(ValueError):verify_image_record(bad,b'xx',record,baseline)
        with self.assertRaises(ValueError):verify_witness(record,witness,data+b'changed')
