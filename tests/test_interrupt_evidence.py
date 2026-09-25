"""Controlled SD-save interruptions (tools/interrupt_evidence.py; G-0001.05 C4)."""
import hashlib
import json
import unittest

from tools.interrupt_evidence import assess


def trial(capture_id, boot):
    return [dict(event='boot', boot_id=boot),
            dict(event='storage_resources', capture_id=capture_id, phase='before_archive', boot_id=boot),
            dict(event='storage_interrupt', chunk=5, boot_id=boot),
            dict(event='boot', boot_id=boot + '-next')]


class FakeDevice:
    def __init__(self, files):
        self.files = files

    def get(self, name):
        if name not in self.files:
            raise FileNotFoundError(name)
        return self.files[name]


def finished(capture_id, raw=b'x' * 100):
    meta = dict(capture_id=capture_id, size_bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    return {capture_id + '.json': json.dumps(meta).encode(), capture_id + '.raw': raw}


class InterruptTests(unittest.TestCase):
    def test_interrupted_saves_are_never_served_and_finished_ones_keep_their_hashes(self):
        runs = [trial(f'ab-{i}-a', f'boot{i}') for i in range(10)]
        files = {**finished('ab-old-a'), **finished('ab-old-b')}
        r = assess(runs, FakeDevice(files), ['ab-old-a', 'ab-old-b'])
        self.assertEqual(r['status'], 'pass', r['errors'])
        self.assertEqual((r['interruptions'], r['served_incomplete'], r['finished_verified']), (10, 0, 2))

    def test_a_served_incomplete_capture_or_a_changed_finished_one_fails(self):
        runs = [trial('ab-1-a', 'b1')]
        files = {**finished('ab-old-a'), 'ab-1-a.raw': b'partial'}
        self.assertEqual(assess(runs, FakeDevice(files), ['ab-old-a'])['status'], 'fail')
        files = finished('ab-old-a')
        files['ab-old-a.raw'] = b'y' * 100
        self.assertEqual(assess(runs, FakeDevice(files), ['ab-old-a'])['status'], 'fail')

    def test_a_trial_without_an_interruption_and_reboot_does_not_count(self):
        run = trial('ab-1-a', 'b1')[:2]
        r = assess([run], FakeDevice(finished('ab-old-a')), ['ab-old-a'])
        self.assertEqual((r['interruptions'], r['status']), (0, 'inconclusive'))


if __name__ == '__main__':
    unittest.main()
