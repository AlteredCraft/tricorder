"""Raw ingress proofs must join to bytes and counters, not just a declaration."""
import copy
import hashlib
import unittest
from tools.investigation import CaptureEvidence, ProtocolError
from test_investigation import evidence

class InvestigationIngressTests(unittest.TestCase):
    def fixture(self):
        meta,raw=evidence()
        before=dict(read_bytes=100,dma_bytes=8000,overflows=2,overwritten_bytes=1024,short_reads=1,read_errors=1)
        after={**before,'read_bytes':100+len(raw),'dma_bytes':8000+len(raw)}
        meta.update(ingress_before=before,ingress_after=after,ingress_blocks=[
            dict(source_start_frame=0,frames=960,read_end_us=20000,sha256=hashlib.sha256(raw).hexdigest())])
        return meta,raw

    def test_verified_proofs_and_legacy_synthetic_fixture(self):
        CaptureEvidence.from_pcm(*self.fixture())
        CaptureEvidence.from_pcm(*evidence())

    def test_tampered_proofs_counters_missing_and_extent_rejected(self):
        meta,raw=self.fixture()
        variants=[]
        for key in ('overflows','overwritten_bytes','short_reads','read_errors'):
            m=copy.deepcopy(meta);m['ingress_after'][key]+=1;variants.append(m)
        for key,value in [('sha256','0'*64),('frames',959),('source_start_frame',1),('read_end_us',99)]:
            m=copy.deepcopy(meta);m['ingress_blocks'][0][key]=value;variants.append(m)
        m=copy.deepcopy(meta);del m['ingress_before'];variants.append(m)
        m=copy.deepcopy(meta);m['ingress_after']['read_bytes']-=1;variants.append(m)
        m=copy.deepcopy(meta);m['ingress_blocks']=[];variants.append(m)
        for m in variants:
            with self.subTest(metadata=m),self.assertRaises(ProtocolError):CaptureEvidence.from_pcm(m,raw)

    def test_declared_warmup_is_outside_raw_but_inside_driver_epoch(self):
        meta,raw=self.fixture()
        meta.update(warmup_frames=24000,epoch_start_us=0)
        meta['ingress_after']['read_bytes']+=24000*8
        meta['ingress_after']['dma_bytes']+=24000*8
        CaptureEvidence.from_pcm(meta,raw)
        for patch in [{'warmup_frames':23999},{'epoch_start_us':101},{'warmup_frames':True}]:
            with self.subTest(patch=patch),self.assertRaises(ProtocolError):
                CaptureEvidence.from_pcm({**meta,**patch},raw)
