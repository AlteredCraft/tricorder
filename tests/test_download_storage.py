import hashlib
import unittest
from tools.download_storage import validate_capture, public_name


class DownloadStorageTests(unittest.TestCase):
    def test_integrity_and_untrusted_listing(self):
        raw=b'1234'
        metadata={'capture_id':'ab-test-a','size_bytes':4,'sha256':hashlib.sha256(raw).hexdigest()}
        validate_capture('ab-test-a',metadata,raw)
        for bad in [b'123', b'1235']:
            with self.assertRaises(ValueError):validate_capture('ab-test-a',metadata,bad)
        with self.assertRaises(ValueError):validate_capture('ab-other',metadata,raw)
        for name in ['../wifi.json','wifi.json','ab-x.raw.part','ab-x/../wifi.json','ab-x%2f.raw']:
            self.assertFalse(public_name(name))
        self.assertTrue(public_name('ab-test-a.json'))
