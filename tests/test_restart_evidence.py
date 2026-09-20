import copy
import unittest

from tools.restart_evidence import assess_software_resets, REQUIRED_CHECKS


class RestartEvidenceTests(unittest.TestCase):
    def fixture(self):
        events=[]
        for cycle in range(11):
            boot=f'boot-{cycle}'
            local=[{'event':'boot','reset_reason':3 if cycle else 11,'firmware':'test-build'}]
            if cycle:
                local.append({'event':'software_reset_resumed','series_id':123,'cycle':cycle})
            for check in REQUIRED_CHECKS:
                local.append({'event':'check','check':check,'result':'pass'})
            local.append({'event':'software_reset_requested' if cycle<10 else 'software_reset_complete',
                          'series_id':123,'cycle':cycle+1 if cycle<10 else 10})
            events.extend(dict(e,boot_id=boot,seq=i,device_us=i*100) for i,e in enumerate(local))
        return events

    def test_ten_actual_software_resets_with_all_checks_pass(self):
        result=assess_software_resets(self.fixture())
        self.assertEqual(result['status'],'pass')
        self.assertEqual(result['software_reset_boots'],10)

    def test_usb_reset_missing_boot_or_completion_cannot_pass(self):
        events=self.fixture()
        for mutate in ('usb','missing','completion','firmware'):
            altered=copy.deepcopy(events)
            if mutate=='usb': altered[next(i for i,e in enumerate(altered) if e['boot_id']=='boot-5')]['reset_reason']=11
            elif mutate=='missing': altered=[e for e in altered if e['boot_id']!='boot-5']
            elif mutate=='firmware': altered[next(i for i,e in enumerate(altered) if e['boot_id']=='boot-5')]['firmware']='different'
            else: altered.pop()
            self.assertNotEqual(assess_software_resets(altered)['status'],'pass',mutate)

    def test_missing_or_failed_capability_is_not_borrowed_from_another_boot(self):
        for result in ('fail','inconclusive'):
            events=self.fixture()
            next(e for e in events if e['boot_id']=='boot-5' and e['event']=='check')['result']=result
            self.assertNotEqual(assess_software_resets(events)['status'],'pass')

    def test_duplicate_request_wrong_series_and_sequence_gap_fail(self):
        for mutate in ('duplicate','series','gap','reused'):
            events=self.fixture()
            if mutate=='duplicate':
                next(e for e in events if e['boot_id']=='boot-4' and e['event']=='software_reset_requested')['cycle']=4
            elif mutate=='series':
                next(e for e in events if e['event']=='software_reset_resumed')['series_id']=999
            elif mutate=='gap': events[2]['seq']+=1
            else:
                for e in events:
                    if e['boot_id']=='boot-5':e['boot_id']='boot-4'
            self.assertEqual(assess_software_resets(events)['status'],'fail',mutate)
