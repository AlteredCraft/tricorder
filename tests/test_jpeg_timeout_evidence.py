import json
import unittest

from tools.jpeg_timeout_evidence import assess_timeout, GUARD_REASON, DRIVER_TIMEOUT


class JpegTimeoutEvidenceTests(unittest.TestCase):
    def fixture(self):
        def event(boot, seq, kind, **fields):
            return 'TRICORDER '+json.dumps(dict(boot_id=boot,seq=seq,device_us=seq*100,event=kind,**fields))
        return [event('a',0,'boot',reset_reason=11,firmware='fixture'),
                event('a',1,'check',check='jpeg_timeout_fixture_armed',result='pass'),
                DRIVER_TIMEOUT, GUARD_REASON,
                event('b',0,'boot',reset_reason=4,firmware='fixture'),
                event('b',1,'check',check='jpeg_timeout_fixture_skipped',result='pass'),
                event('b',2,'check',check='jpeg_initialize',result='pass')]

    def test_expected_fault_is_not_workload_acceptance(self):
        result=assess_timeout('\n'.join(self.fixture()))
        self.assertEqual(result['status'],'pass')
        self.assertFalse(result['workload_acceptance'])

    def test_missing_any_required_observation_cannot_pass(self):
        for index in range(7):
            lines=self.fixture();lines.pop(index)
            self.assertNotEqual(assess_timeout('\n'.join(lines))['status'],'pass',index)

    def test_wrong_reset_failure_and_sequence_gap_fail(self):
        for before,after in [('"reset_reason": 4','"reset_reason": 11'),
                             ('"result": "pass"','"result": "fail"'),
                             ('"seq": 2','"seq": 3'),
                             ('"firmware": "fixture"','"firmware": "other"')]:
            lines=self.fixture();lines[4:]=[s.replace(before,after) for s in lines[4:]]
            self.assertEqual(assess_timeout('\n'.join(lines))['status'],'fail')

    def test_wrong_order_repeated_panic_or_rearming_fails(self):
        for mode in ('order','panic','rearm'):
            lines=self.fixture()
            if mode=='order': lines[2],lines[3]=lines[3],lines[2]
            if mode=='panic': lines.append(GUARD_REASON)
            if mode=='rearm': lines[5]=lines[5].replace('fixture_skipped','fixture_armed')
            self.assertEqual(assess_timeout('\n'.join(lines))['status'],'fail',mode)

    def test_malformed_instrumentation_fails(self):
        self.assertEqual(assess_timeout('\n'.join(self.fixture()+['TRICORDER {']))['status'],'fail')
